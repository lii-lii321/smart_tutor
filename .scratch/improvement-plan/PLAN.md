# 全面提升方案（2026-09-09 夜间执行版）

> 定位：上一轮（48 文件）已修复资金并发/部署阻断/安全守卫等问题。本方案覆盖**剩余全部已知提升点**，
> 按优先级分层，每项含现状证据、文件级改动、验收标准、估时。P0 可无人值守夜间执行，
> P1 建议有人值守逐项做，P2/P3 需要决策或外部条件（MySQL 连接、Sentry DSN、产品确认）。

---

## 0. 执行协议（夜间执行者的硬规则）

1. **每项一个独立 commit**，格式 `chore|feat|fix(scope): 简述`，commit message 末尾附 `[PLAN:P0-1]` 标记。
2. 每完成一项必须跑：`python -m pytest tests/ -q`（后端项）和 `cd frontend && npm run build`（前端项）。任何一项红了，先修再走，修不动就回滚该项并跳过。
3. 单项卡壳超过 30 分钟 → 回滚该项改动，在本文件末尾「执行日志」记录原因，继续下一项。
4. **红线（一律不做）**：
   - 不改 `services/calculator.py` 的任何费率与公式语义（只读）。
   - 不删除 `database.py` 的 `_ensure_*` 补丁（P2-1 才退役，且需 MySQL 对账前置）。
   - 不启用 Redis 密码（牵连所有部署的 REDIS_URL）。
   - 不动 API 路径与既有字段名（只加不改，向后兼容）。
   - P1-1 的 Board.vue 拆分必须独占一个会话，不与其他项混做。
   - 不引入新框架（状态管理/CSS/ORM 等）；工具链依赖（ruff/vitest 等）不受限。
5. 全部完成后在「执行日志」写汇总：完成清单 / 跳过清单 / 遗留风险。
6. **断点续跑（必须执行）**：开始前创建 `.scratch/improvement-plan/STATE.md`（勾选清单 + 当前进行项 + 时间戳），
   **每 commit 一项立即更新**。任何新会话（含断电重启后）接管时：先读 PLAN + STATE + `git log --oneline -15`，
   再跑 `python -m pytest tests/ -q` 与 `cd frontend && npm run build` 确认工作区状态；
   若存在上一个会话留下的未提交半成品，先评估——能小步补完就补完提交，不能就 `git checkout` 回滚该项，从 STATE 的断点继续。
   注意：未提交的工作区改动在断电/重启后**不会丢失**（git 工作区是持久化的），最坏情况只是"半成品未验证"，不是进度清零。
7. **大项内部小步提交**：单项超过 60 分钟的（P0-3、P0-4、P0-6）必须拆成 ≥2 个 commit
   （如 P0-3：conftest 基座一个 commit、回归测试一个 commit），把断电窗口压到 30 分钟以内。
8. **硬停止规则**：到达停止时间后**不开始任何新项**；正在做的项做完提交（或安全回滚）后立即收尾。
   防止在电量耗尽边缘留下半成品。

---

## A. P0 · 今晚执行（低风险基建，约 6~7 小时）

### P0-1 日志体系落地（估时 40min）

**现状证据**：全仓库无任何 logging 配置（`basicConfig|dictConfig` 匹配为 0）。
`routers/v1/orders.py`、`services/parser.py`、`services/scheduler.py`、`middleware/rate_limit.py`、
`routers/v1/public.py` 均使用 `logger.info/warning/exception`，但根 logger 无 handler——
INFO 级全部丢弃，WARNING 以上走 lastResort 裸吐 stderr，无时间戳格式、无级别控制、无文件落盘、无轮转。
上一轮修的「Redis 降级留日志」「AI 异常入日志」在当前配置下实际上**看不见**。

**改动**：
- 新增 `utils/logging_config.py`：`setup_logging()` 用 `dictConfig`——
  控制台 handler + `TimedRotatingFileHandler(logs/app.log, when="midnight", backupCount=14)`，
  格式 `%(asctime)s %(levelname)s [%(name)s] %(message)s`；
  对 `uvicorn.access`、`uvicorn.error` 复用同一格式。
- `config.py` 加 `LOG_LEVEL: str = "INFO"`、`LOG_DIR: str = "logs"`。
- `main.py` lifespan 最前调用 `setup_logging()`。
- `docker-compose.yml` 四个服务加 `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}`。
- `.gitignore` 已有 `*.log`，无需改。

**验收**：DEV_MODE 启动后 `logs/app.log` 存在且有启动日志；触发一次登录失败能看到 WARNING；
`docker compose config` 语法通过。

### P0-2 Ruff 接入 + CI lint 步骤（估时 30~60min）

**现状证据**：`requirements-dev.txt` 仅 `pytest==9.1.1`、`pytest-asyncio==1.4.0`；仓库无任何 Python linter；
`.github/workflows/ci.yml` 后端 job 只装依赖→跑测试。

**改动**：
- `requirements-dev.txt` 加固定版本 `ruff==0.6.x`（查当日最新 pin 死）。
- 新增 `pyproject.toml`：`[tool.ruff] line-length=100, target-version="py311"`；
  `[tool.ruff.lint] select=["E","F","I","B","UP","SIM"]`，`ignore=["E501"]` 视情况；
  同时把 pytest-asyncio 的 `asyncio_mode = "auto"` 配置在这里（服务 P0-3）。
- 先 `ruff check --fix .` 清存量（预计集中在 import 排序与未用导入），人工过一遍 diff。
- `ci.yml` 后端 job 在测试前加 `ruff check .`。
- `pyproject.toml` 顺带加 `[tool.pytest.ini_options] testpaths=["tests"]`。

**验收**：`ruff check .` 0 error；CI 绿。

### P0-3 测试基座：conftest + pytest-asyncio 统一 + 5 个防退化回归（估时 90min）

**现状证据**：`tests/` 13 个文件、**无 conftest.py**（实测 0 个）；"临时文件 SQLite + env 注入 + _fresh_db()"
样板在 `test_business_features.py:16-54`、`test_money_flow.py:25-51`、`test_regressions.py:23-48` 等 12+ 处重复；
pytest-asyncio 装而未用，全部 `asyncio.run()` 手动驱动。

**改动**：
- `tests/conftest.py`：
  - 模块级最先注入 env（`JWT_SECRET=tests-secret-...`、`DEV_MODE=true`、`AUTO_CREATE_SCHEMA=false`）；
  - `db_engine` fixture：每用例独立临时 SQLite（`sqlite+aiosqlite` 内存或 tmp_path）+ `Base.metadata.create_all`；
  - `db` / `client` fixture：`AsyncSession` + httpx `AsyncClient(transport=ASGITransport(app))`；
  - `make_tenant` / `make_teacher` / `make_order` 工厂函数（吸收各文件重复的造数代码）。
- 存量文件**只迁 2~3 个**（选 test_smoke / test_production_guards / test_money_flow）做样板，其余留 P1。
- 补 5 个防退化回归（对应上轮修复，全部缺失）：
  1. 非 DEV_MODE 下 `JWT_SECRET=""` 或短于 32 位 → `Settings()` 抛 RuntimeError（`test_production_guards.py` 扩展）。
  2. `is_active=false` 的中介：`/auth/teacher-phone-login`、`/auth/teacher-phone-register` 均 403。
  3. `/financial-records/mine?page=1&page_size=1` 只返回 1 条但 `total_paid` 等汇总仍为全量值。
  4. `/applications/reviews/mine?page_size=1` 分页生效。
  5. `/applications/{id}/trial-failed?refund_amount=10.005` → 落库 `refund_out` 金额为 `10.01`（Decimal 舍入）。

**验收**：pytest 全绿且用例净增 ≥5；conftest 样板可被新测试直接复用。

### P0-4 CI 增强：alembic check 防模型漂移 + 依赖审计 + MySQL job（估时 90min）

**现状证据**：CI 已有迁移链 round-trip（上轮加的）；但 models 与迁移的漂移无检查；
依赖无漏洞扫描（无 pip-audit/npm audit）；MySQL 方言 0 CI 覆盖（本地 alembic 1.19.1 支持 `alembic check`）。

**改动**：
- ci.yml 迁移验证步骤末尾追加 `alembic check`。若首次运行报存量漂移（很可能，因 `_ensure_*`
  与 alembic 双轨），把 diff 输出贴到本文件「执行日志」，**不要**为消 diff 临时造迁移——转 P2-1 处理；
  该 step 加 `continue-on-error: true` 并打产出物，两周内清零后改为阻塞。
- 后端 job 加 `pip install pip-audit && pip-audit -r requirements.txt`（发现漏洞只记录不阻塞，产出物上传）。
- 前端 job 加 `npm audit --audit-level=high`（只报 high+，防噪音）。
- 新增 `mysql` service job（`mysql:8.4` + healthcheck `mysqladmin ping`）：
  env 指向 MySQL 跑 `alembic upgrade head` + `alembic downgrade base` + `alembic upgrade head`，
  再跑 `pytest tests/test_smoke.py -q`（DATABASE_URL 用 `mysql+aiomysql`）。
  注意：现有测试写死 SQLite 临时文件，全量套件进 MySQL job 要等 conftest 迁移完成，本轮不放开。

**验收**：CI 三 job 全绿；本地临时在 models 加一列（不建迁移）能观察到 `alembic check` 报错，随后还原。

### P0-5 nginx 安全响应头 + index.html 缓存策略（估时 20min）

**现状证据**：`deploy/nginx.conf` 无 `X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`；
`location /`（SPA 入口）无 Cache-Control，发版后 index.html 可能被缓存引用已删除的 chunk
（前端虽有 router.onError 刷新兜底，但应从源头消除）。CSP 本轮**不做**（AMap/Vant 内联与外链脚本多，需单独评估，见 P2-8）。

**改动**：
- server 块加三个安全头；
- `location /` 加 `add_header Cache-Control "no-cache";`（`/assets/` 已是 immutable，不动）。

**验收**：`docker compose build web && up` 后 `curl -I` 能看到三个头；index.html 响应带 no-cache。

### P0-6 补齐 response_model，闭环 OpenAPI 契约（估时 60~90min）

**现状证据**（逐条核实，17 个路由无 response_model）：
`orders.py "/"`（订单列表）、`applications.py "/summary"`、`auth.py` 4 个（change-password×2、/me、/me/profile）、
`notifications.py` 4 个、`tenants.py` 3 个（my-teachers/export、blacklist-status、teachers/{id}/blacklist）、
`resumes.py "/{resume_id}"`。CSV 导出类 4 个不适用（StreamingResponse），跳过。

**改动**：
- `models/schemas.py` 新增：`NotificationResponse`（若已有则复用）、`OrderListResponse`（items/page/page_size/total，
  与 `frontend/src/api/types.ts` 对齐）、`ApplicationSummaryResponse`、`MeProfileResponse`、
  `BlacklistStatusResponse`、`TenantTeacherListResponse` 等。
- 逐路由补 `response_model=`。行为零变化（FastAPI 会按模型过滤输出，需核对各响应字段是否被截断——
  对 `/me/profile` 这类动态结构可用 `response_model=None` + 文档注释明确豁免）。
- 这一步是后续「前端类型从 OpenAPI 自动生成」的前置。

**验收**：pytest 全绿；DEV_MODE 下抽查 `/openapi.json` 中上述路径出现 schema 引用。

### P0-7 Dependabot（估时 15min）

**改动**：新增 `.github/dependabot.yml`：`pip`、`npm`（directory `/frontend`）、`github-actions` 三个
package-ecosystem，weekly，`open-pull-requests-limit: 5`。

**验收**：YAML 语法通过（`python -c "import yaml,sys; yaml.safe_load(open('.github/dependabot.yml'))"`，PyYAML 若无则跳过）。

### P0-8 前端类型收口：notifications + 视图 any[]（估时 60~90min）

**现状证据**：`api/orders.ts`、`applications.ts`、`financial.ts` 已类型化（上轮完成），但
- `api/notifications.ts` 的方法无返回类型标注；
- 视图层仍有 `ref<any[]>`（`OrdersList.vue:10`、`ApplicationsReview.vue:12-13`）与 `res: any`（`OrdersList.vue:34`）。

**改动**：
- notifications.ts 补 `Promise<NotificationItem[]>` 等标注；
- 视图 `ref<any[]>` → `ref<OrderBrief[]>` / `ref<ApplicationItem[]>`（类型从 `@/api/types` 引入），
  `vue-tsc` 连带报错逐个修（预计是对可选字段的直接访问改 `?.`）；
- 顺手清理 `components.d.ts` 之外的遗留 `: any` 参数标注（仅限改类型不改逻辑）。

**验收**：`npm run build` 通过；`grep -rn "ref<any" frontend/src` 结果为 0 或仅剩注释引用。

---

## B. P1 · 本周执行（结构收敛与体验，约 12 小时）

### P1-1 Board.vue 拆分（1081 行 → 组合式结构）（估时 3~4h，独占会话）

**现状证据**：`views/teacher/Board.vue` 1081 行、约 37 个函数：地图初始化/销毁、中介选择器、
城市选择、学段筛选、推荐列表、订单 sheet 全在一个文件，改一处要在千行文件里找上下文。

**目标结构**：
```
src/composables/useAMap.ts                    # 地图初始化/销毁/marker/高亮定位（约300行逻辑）
src/components/teacher/AgentPicker.vue        # 中介切换（+localStorage 记忆）
src/components/teacher/CityPicker.vue         # 城市选择
src/components/teacher/OrderSheet.vue         # 订单详情底部弹层
src/components/teacher/RecommendList.vue      # 推荐卡片列
```

**步骤**：先抽 `useAMap`（纯逻辑、map 实例由外部注入）→ 逐组件搬移（明确 props/emit 边界）→
Board.vue 只留数据编排。每拆一个组件跑 build + DEV_MODE 手动冒烟
（地图渲染、推荐卡点击高亮定位、订单 sheet 打开、城市/中介切换）。

**风险**：地图生命周期（onUnmounted 销毁、AMap 热更新内存泄漏）。夜间无人值守**不做此项**。

### P1-2 ApplicationsReview.vue 拆分 + 状态文案常量化（估时 2h）

**现状证据**：893 行；投递状态→文案/颜色映射在 `ApplicationsReview.vue:512、:713` 两处**完全相同**的
内联对象强转 `as any`，`MyApplications.vue:70`、`OrderDetail.vue:49` 又各一份不同结构。

**改动**：`src/constants/applicationStatus.ts` 唯一导出 `Record<ApplicationStatus, {label, color}>`
与 `applicationStatusLabel(s)`；四个视图全部改为引用；`ApplicationDetailDialog.vue` 拆出详情弹窗（约 300 行）。

**验收**：build 通过；四视图文案渲染不变（人工比对一遍状态枚举全覆盖，特别是 `forfeited`）。

### P1-3 后端订单序列化单点化，4 处重复 → 1（估时 90min）

**现状证据**：字段映射四处各写一份——`orders.py:_build_order_detail`（34-68）、
`orders.py list_orders` 内联 dict（541-561）、`public.py:_build_order_brief`（21-41）、
`services/recommendation.py`（375-414）。金额转 float、坐标脱敏（coarse_coordinate）、
needs_manual_price 判断等规则改一处漏三处。

**改动**：新增 `services/serializers.py::order_fields(order, *, sensitive: bool) -> dict`；
四处改调用。**硬约束：输出与旧实现逐字段相等**——先写一次性等价性测试
（同一批订单对象分别跑新旧函数 `assertEqual`），绿了再删旧代码。

### P1-4 租户隔离守卫收敛（估时 60min）

**现状证据**：`if payload.role != "super_admin" and x.tenant_id != payload.tenant_id: 404` 样板散落
`orders.py:79、:299`、`applications.py:182、:472`、`financial_records.py:62、:77、:148`、
`notifications.py:85、:95`、`tenants.py:379` 等 10+ 处，新路由漏写即越权。

**改动**：`middleware/auth.py` 新增
`def assert_tenant_scope(payload: TokenPayload, tenant_id: int | None) -> None`（语义保持 404 防探测）
与可选的 `def tenant_scoped(query, payload)` 查询助手；逐处替换，行为零变化。

### P1-5 usePagedList composable（估时 90min）

**现状证据**：`OrdersList.vue:11-63` 与 `FinancialRecords.vue:10-114` 各自实现
loading/loadingMore/page/known Set 去重，结构 90% 相同，hasMore 边界各自维护。

**改动**：`src/composables/usePagedList.ts` 输出 `{items, loading, loadingMore, hasMore, load, loadMore, reset}`，
两视图接入。已知差异点：FinancialRecords 带 filters（类型/日期），fetcher 设计成 `(page, pageSize) => Promise<{items, hasMore}>` 即可覆盖。

### P1-6 前端健壮性三件套（估时 2h）

1. **骨架屏**：全项目 `van-skeleton` 0 处；Board 推荐卡区、OrdersList 列表、ApplicationsReview 列表首屏各加。
2. **错误边界**：`main.ts` 注册 `app.config.errorHandler`（console + 上报钩子 + 通用 toast 兜底），
   防止单组件渲染异常白屏。
3. **GET 重试**：`client.ts` 手写约 30 行——仅 GET、无重试标记头、网络层错误（无 response）时退避 400ms 重试一次；
   幂等安全，不碰写请求。

### P1-7 scheduler 独立部署单元（估时 45min）

**现状证据**：调度内嵌 api 进程（`main.py:16` lifespan，`Dockerfile:17 --workers 2` 每进程一份），
靠上轮加的 Redis NX 锁互斥。职责上调度不该在 API 进程里。

**改动**：`services/scheduler_main.py`（`if __name__ == "__main__": asyncio.run(loop())`）；
`main.py` lifespan 读 `config.DISABLE_SCHEDULER`（默认 false）；compose 加 `scheduler` service
（同镜像、`DISABLE_SCHEDULER` 不设、command 覆盖、replicas 隐式 1）；api service 设 `DISABLE_SCHEDULER: "true"`。
本地开发不受影响。

### P1-8 agent_board 30s 响应缓存（估时 60min）

**现状证据**：`public.py:44` 橱窗接口无登录、无频率限制，每次都走 Redis GEO + MySQL `IN` 查询；
地图页自动刷新/多人同时打开会对 DB 形成无区分度压力。

**改动**：`Redis SET board:{tenant_id} EX 30`（value 为序列化后的 AgentBoardResponse），
命中直返；失效钩子挂在写路径已有坐标同步处（`orders.py` 的 batch_sync/remove 调用点、
`order_maintenance.archive_expired_recruiting_orders`）顺带 `DEL board:{tenant_id}`。

**验收**：日志观察二次请求耗时 <5ms；导入新订单后刷新橱窗立即可见（DEL 生效）。

### P1-9 错误上报 Sentry（估时 45min）

**改动**：requirements 加 `sentry-sdk[fastapi]`（pin）；frontend 加 `@sentry/vue`；
DSN 均从 env 读（`SENTRY_DSN` / `VITE_SENTRY_DSN`），**未配置时完全 no-op**（本地零感知）；
后端在 main.py lifespan 初始化，traces_sample_rate=0.1；前端在 main.ts init 并挂到 P1-6 的 errorHandler。

---

## C. P2 · 两周内（架构债清偿与深度保障，约 3~4 天）

### P2-1 database.py 双轨收敛（约 300 行 `_ensure_*` 退役）

**现状证据**：`database.py:85-385` 十余个 `_ensure_*` 闭包（含 notifications 整表重建）与 alembic/versions 一一重复，
靠 create_all+inspector 兜底；两套事实源必然漂移，且 `AUTO_CREATE_SCHEMA` 一旦误开会在生产跑 delete/DDL。

**前置条件**：能连 MySQL。**步骤**：
1. 干净 MySQL 跑 `alembic upgrade head` 得到「迁移基准 schema」；
2. 写 `scripts/schema_diff.py`：对目标库与基准做 information_schema 全量对账（列/类型/索引/约束）；
3. 对现网（或长期开发库）跑 diff → 差异即 `_ensure_*` 曾修的问题清单，逐一确认已进迁移；
4. diff 为空后删除 `_ensure_*`；DEV_MODE 的 `init_db` 改为执行 `alembic upgrade head`（env.py 已兼容 SQLite）；
5. CI 的 `alembic check` 从 continue-on-error 改为阻塞。

### P2-2 前端测试体系从 0 到 1

**现状证据**：package.json 无 vitest/@vue/test-utils/测试脚本；CI 前端只有 build。
**改动**：vitest + happy-dom + @vue/test-utils（全 pin）；首测目标纯逻辑——
`utils/format`（边界：null/负数/千分位）、`utils/apiError`（422 数组/网络错误/Error 分支）、
`stores/auth` 的 fetchMe 缓存与失败不缓存、`usePagedList` 边界；
CI 前端 job 加 `npm run test -- --run`。估时 2~3h。

### P2-3 Playwright E2E 冒烟

场景链：教员登录 → 橱窗浏览 → 投递 → 中介登录 → shortlist → confirm-deposit。
订单解析用带 ID 的轻量解析路径（`parser._parse_labeled_orders`）绕开 DeepSeek 依赖；
`e2e/` 目录 + `workflow_dispatch` 手动触发，不挡 PR。估时半天。

### P2-4 property-based 测试（hypothesis）

- calculator：任意合法 base_price，输出恒两位小数、`deposit+balance == total` 恒等、total ≥ DEPOSIT。
- state_machine：任意 (current, target, role) 组合只抛 ValueError/PermissionError 两种；
  废弃状态（pending_deposit 等）永不为合法目标。
- 入 CI（快，秒级）。估时 90min。

### P2-5 metrics 与容量基线

`prometheus-fastapi-instrumentator` 挂 `/metrics`——**必须**与 docs 同样 gate（生产不可公开暴露）；
业务计数器：解析次数/耗时分布、投递创建、按 operator_role 的资金操作计数；
`deploy/grafana/` 放看板 JSON。若无 Prometheus 条件，降级方案：超管鉴权的 `/internal/stats`。
同期跑一次 locust 压测（board/推荐/列表三接口）留基线数据。估时半天。

### P2-6 资金操作审计日志

**现状证据**：`financial_records` 仅 `operator_role`，无法回答"谁、何时、哪个 IP 确认的收款/退款"。
**改动**：新表 `audit_logs(id, tenant_id, actor_role, actor_id, action, object_type, object_id, ip, created_at)`
+ 索引 `(tenant_id, created_at)`；在 confirm_deposit / confirm_balance / trial_failed / forfeit /
cancel 五个写路径追加写入（不改既有响应）；超管查询接口 + 分页。
迁移走 alembic 新 revision。估时 3h。

### P2-7 PII 与账号生命周期

- **教员注销流程**（合规刚需）：软删 + 手机号脱敏存档（如 `138****0001` + hash 保留防重复注册）+
  投递/流水保留但姓名联系方式匿名化。路由 `DELETE /auth/teacher/account` + 确认机制。
- **家长电话/地址静态加密 ADR**：AES-GCM、密钥走 env 轮换方案、address-unlock 时解密——
  先写 `docs/adr/0001-pii-encryption.md` 决策，评审后再实施。
估时：注销半天；加密 ADR 2h + 实施另计。

### P2-8 CSP 分阶段上线

先 `Content-Security-Policy-Report-Only`（允许 AMap 域名、unsafe-inline 过渡）观察一周日志，
再收紧 enforce。与 P0-5 的三个基础头互补。估时 2h + 观察期。

---

## D. P3 · 战略项（按需排期）

| 项 | 说明 | 前置 |
|---|---|---|
| staging 环境 | `compose.prod.yml` + 独立主机，发布前冒烟 | 服务器 |
| 发布流程 | semver tag + git-cliff 自动 CHANGELOG；compose 补 `image:` 命名（当前 build 无镜像名，只能本地 tag） | 无 |
| 游标分页 | notifications 现状仅 `limit`（上限 100）无翻页，量大后「加载更多」做不了 | 产品确认交互 |
| 订单搜索增强 | 现状仅 raw_id LIKE；多字段（科目/年级/地址）筛选需产品定优先级 | 产品确认 |
| 时区治理 ADR | 全库存 naive UTC（`middleware/auth.py:84` calendar.timegm 注释可见踩坑史），固化约定 + tz-aware 迁移预案 | 无 |
| 文档补齐 | AGENTS.md 约定的 root `CONTEXT.md` + `docs/adr/` 未建立；至少补 3 篇 ADR：资金状态机、脱敏与解锁卡点、Redis 降级策略 | 无 |
| 托管数据库 | 自建 MySQL 容器 → 云 RDS（自动备份/高可用） | 成本决策 |

**已评估后排除**（记录原因，防止反复讨论）：
- Redis 密码：compose 内网隔离且无对外端口，启用需改所有环境的 REDIS_URL，收益不抵破坏性；
- i18n：单语产品；
- 微服务化/读写分离：当前量级（演示/初创）远未到；
- 简历文件上传与对象存储：简历为文本表单，无文件面。

---

## E. 夜间执行 Runbook（照此顺序）

```
1. P0-1 日志体系          → commit → pytest
2. P0-2 ruff + pyproject  → commit → ruff check + pytest
3. P0-7 dependabot        → commit
4. P0-5 nginx 安全头      → commit
5. P0-6 response_model    → commit → pytest
6. P0-3 conftest + 回归   → commit → pytest（用例数应增加）
7. P0-4 CI 增强           → commit（注意 alembic check 首跑可能报存量漂移：记录，不阻塞）
8. P0-8 前端类型收口      → commit → npm run build
```

### E-1. 今晚 23:00 场景（电量受限，裁剪版）

- **今晚范围（4 项，约 3.5~4h）**：P0-1 → P0-2 → P0-7 → P0-3 → P0-4（有余力才继续，否则停）。
- **硬停止时间：02:30**。到点不开始新项，当前项收尾提交即结束。
- P0-5 / P0-6 / P0-8 顺延到明天白天，用 STATE.md 断点续跑。
- 断电应对分层（照做则最坏只损失 30 分钟）：
  1. 已提交项天然安全（一项一 commit）；
  2. 未提交半成品不会因断电丢失，续跑会话先用 pytest 评估再决定补完或回滚；
  3. 大项内部小步提交把风险窗口压到 ≤30 分钟（协议第 7 条）。
- **执行机要求**：插电源运行；执行前关闭睡眠——
  `powercfg /change standby-timeout-ac 0` 与 `powercfg /change hibernate-timeout-ac 0`；
  电池低电量自动休眠保留不动（那是兜底，git 状态扛得住休眠/断电）。

- 每步之间全量 `pytest` + `npm run build` 双闸。
- 预计总耗时 6~7 小时，若夜间时间不足，优先保证 1/2/3/6/7 完成。
- **P1 全部不建议无人值守过夜执行**（涉及行为等价性验证与 UI 冒烟）；如夜间有空窗，
  可做 P1-3/P1-4/P1-7（后端、有等价性测试兜底的项），P1-1 必须留给白天的独立会话。

---

## 执行日志（执行者填写）

```
日期：2026-09-09 23:02 ~ 00:30（夜间会话，电量续跑）
完成：baseline(aaddbcc)、P0-1(c5ab60b)、P0-2(5ddf817)、P0-7(ce80591)、P0-3(1eaf954+1653dfb)、
      P0-4(dd97bde)、P0-5(5c20106)、P0-6(0aeacf3)、P0-8(7247dab)、时区测试修复
跳过：无——P0 全部 8 项完成
alembic check 存量漂移记录：本地 SQLite 实测「No new upgrade operations detected」——无漂移，
  因此 CI 中 SQLite 检查直接设为阻塞；MySQL 检查因方言差异设 continue-on-error 观察期。
pip-audit / npm audit 发现：CI 首跑后看 Actions 日志（本地未装 pip-audit，留待 CI 记录）。
重要发现（真实产品缺陷证据）：
  财务日期筛选在跨午夜场景查不到记录——created_at 存 naive UTC，而前端/测试用本地日期
  （date.today()）。东八区每天 0:00-8:00 期间，"今天"筛选实际查不到刚发生的流水。
  测试已改为 UTC 口径修复 flaky；产品侧按本地时区筛选的诉求转入 P3 时区治理 ADR 决策。
遗留风险：
  1. P0-2 中 ruff 规则做了保守裁剪：E501(175处长行)、SIM105(32处)、UP042(4处) 已 ignore；
     per-file 豁免：main.py E402（刻意的路由注册顺序）、tests B011/E702/F841/B007、scripts F841/B007、
     alembic UP007/UP035。后续可单独跑 ruff format 一轮收 E501。
  2. F821 修复：tests/test_business_features.py 的 __main__ 块删除了对已不存在函数
     test_exports_and_blacklist_status 的调用（pytest 收集不受影响）。
  3. F841 顺带清理：services/recommendation.py 删除死变量 best_resume/source_resume
     （下游实际使用的是 best_resume_payload，无行为变化，全量测试验证）。
  4. P0-3 新增测试与存量测试共享进程内限流桶（ASGI 客户端 IP 为 unknown），
     已用 monkeypatch 在新用例内局部放宽 MAX_LOGIN_PER_MINUTE，不影响存量 429 断言。
  5. TimedRotatingFileHandler 在 Windows 多进程下轮转可能因文件锁失败（生产为 Linux 容器，
     本地开发单进程，影响有限）。
  6. P0-8 范围说明：Board.vue/MapBoard.vue/amap.ts 的 AMap 域 any 有意保留（无官方类型，
     且 Board 拆分是 P1-1 独立会话的事）；Typescript 收口发现 TeacherSummary 契约盲区
     （前端缺 gender/phone/信用画像等 10 字段），已在 types.ts 对齐后端 schemas.py。
测试基线：75 passed，ruff check 全绿，npm run build（含 vue-tsc）通过。
```

### 续跑补充（2026-09-10 00:42，P1 后端四项）

```
完成：P1-3(db387cd)、P1-4(59dea85)、P1-7(916aea1)、P1-8(1bfd54e)
跳过：P1-1/P1-2（UI 拆分需真机冒烟）、P1-5/P1-6（前端需盯）、P1-9（需 Sentry DSN 决策）
电量执行记录：起点 62%（纯电池，预计续航 213min）→ P1-3 前 59% → P1-4 前 56% → P1-7 前 55% → 收尾 51%。
  满载突发合计仅 6 次全量 pytest + 2 次子集快跑 + 1 次前端构建；
  项间电量闸门未触发（阈值 35%），20% 停止线远未接近。
P1 补充说明：
  7. P1-3 用"契约测试锁定输出"（test_serializers.py，确定性样例锁定坐标脱敏/掩码/needs_manual_price）
     替代一次性等价性脚本，多留一道回归防线；顺带修掉 recommendation 每单重复调用两次
     coarse_coordinate 的浪费。
  8. P1-4 tenant_scoped 保留"无租户 token 不过滤"的历史行为（上游守卫已拦截），零行为变化。
  9. P1-8 失效覆盖：_sync_order_geo finally 钩子（update/archive/republish/batch-status 共用）
     + batch_import/transit 显式调用 + scheduler 归档失效；失效失败由 TTL 30s 兜底。
测试基线：79 passed，ruff 全绿，docker compose config 校验通过。
```

### CI 首跑修复记录（2026-09-10 05:20，白天会话）

```
最终状态：三 job 全绿（Backend tests / MySQL migration round-trip / Frontend build），HEAD = c55c3e7
审计结论：pip-audit「No known vulnerabilities found」；npm audit「0 vulnerabilities」；
  alembic check 在 MySQL 上只报 5 个列注释差异（历史迁移建列无 comment），已在 env.py
  设 compare_comments=False 让 check 只拦真实 schema 漂移。
修复的三类问题（均为新步骤首跑暴露，正是建 CI 的目的）：
  1. MySQL 1553（两轮）：索引迁移的降级在外键列上删索引，破坏外键的索引依赖。
     - d5b9e7c3a1f2：降级先补回 ix_app_tenant/ix_app_order 单列索引再删复合索引；
     - c2a7e9b4d1f3：三个索引同问题，同模式修复；
     - a9a54481a950/a4d8f2e6c9b1/c8f5b2e3a4d6：降级中"先 drop_index 再 drop_table"的索引
       （随表删除即可）删掉单独 drop_index 语句。
     SQLite 不做该检查，所以此前本地 round-trip 全绿——这正是 MySQL job 的价值。
  2. MySQL job 冒烟步骤缺 pytest（只在 requirements-dev），改为 pip install -r requirements.txt pytest==9.1.1。
  3.Dependabot 首轮开出 9 个 PR：安全小版本 3 个（autoprefixer/postcss/alembic）建议合；
     actions 大版本 3 个（checkout/setup-node/setup-python 4/5→7）CI 验证后可合；
     前端大版本 3 个（typescript 5.9→7.0、vue-tsc 2.2→3.3、pinia 2→4）CI 已红，建议关闭留待专项升级。
```

### NIGHT 计划执行日志（2026-09-10 晚，会话 2）

```
计划：NIGHT-2026-09-10.md（4 核心 + 2 备选）——6 项全部完成，无跳过项（除 smoke 迁移因不适用）
完成：
  1. P2-2 vitest 落地（0d0bf52）：vitest 5.0.0 / @vue/test-utils 2.5.0 / happy-dom 20.14.3（pin 死）；
     tests/ 独立目录（format/apiError/authStore），首批 20 用例。
  2. P2-4 hypothesis property tests（109074a）：hypothesis==6.168.0；
     calculator 恒等式（deposit+balance==total、两位小数 Decimal、total>=DEPOSIT、<=0 必拒、
     全域结果有界）+ 状态机全域 (current,target,role) 合法性有界 + 废弃状态永不为合法目标。
     新增 6 用例，总时长 ~3s（<20s 预算）。
  3. P1-5 usePagedList（43179db）：composable + OrdersList/FinancialRecords 接入 + 9 单测。
     两视图手写 loading/page/known 去重样板已消除（验收项）。
  4. P1-6a（a848b6b）：OrdersList/ApplicationsReview 列表 3 行骨架、Board 推荐卡骨架占位、
     main.ts 全局 errorHandler（console + toast 3s 节流）。
  5. P1-6b（59a57b7）：client.ts 响应拦截器对 GET + 无 response + 未重试过的请求退避 400ms 重发一次。
  6. P1-2 弹窗拆分（bb7f1dc）：ApplicationDetailDialog.vue 拆出（props application/show、
     emit update:show/blacklisted）；ApplicationsReview.vue 893→692 行；
     顺带完成状态文案常量化（constants/applicationStatus.ts）与 utils/clipboard.ts 收敛。
  7. 测试迁移 3 文件：test_final_polish（910ef0c）、test_regressions（89d9520）、
     test_money_flow（2dd2f54）——逐文件迁移、每迁一个跑全量 pytest；只换基建不改断言；
     合计净删约 750 行样板。test_smoke 为纯逻辑测试无样板，不适用，跳过。
跳过：无（计划内全部完成；红线项 P1-1 Board 拆分、P1-9 Sentry、P2-1 按计划未动）
重要发现：
  1. usePagedList 初版把 hasMore 的依赖（lastPageCount/totalFromServer）写成普通闭包变量，
     computed 不追踪导致缓存不失效——单测当场抓住，改 ref 修复。教训：computed 依赖必须响应式。
  2. hypothesis 首跑纠正了计划里的两处边界想当然：
     a) base_price∈[0.01,999999] 内低价段会被「低于最低定金」拒绝，恒等式只在成功输出上成立
        （改为「必成区 [125.00,∞) 恒等式 + 全域结果有界」两个 property）；
     b) 1.5 倍费率下「必拒」上界是 66.66 而非 124.99（66.67×1.5=100.005 舍入后过线）。
  3. P0-8 遗留的「状态文案两处重复」实况：APPLICATION_STATUS_LABELS 只在 ApplicationsReview
     内联一份（MyApplications/OrderDetail 是不同结构），本轮已收敛到 constants/applicationStatus.ts。
遗留风险 / 备忘：
  1. P2-2 未改 ci.yml：前端 CI job 还没有 `npm run test -- --run` 步骤，白天 push 前建议补上。
  2. FinancialRecords 接入后 summary（汇总指标）只在第一页响应时整体替换
     （旧行为是 loadMore 后用第 N 页响应覆盖，数值等价；汇总本就不随分页变化）。
  3. usePagedList 无 total 时 hasMore 按「末页不满」推断（lastPageCount>=pageSize），
     与旧版 FinancialRecords 的 accumulated>=page*pageSize 在"整页全是重复项"的病态场景下略有差异。
  4. errorHandler 的 toast 依赖 vant 运行时挂载，模块首加载即注册，无 SSR 场景，风险低。
  5. GET 重试对超时（ECONNABORTED）同样生效（无 response 即重试）；写请求不受影响。
  验收基线达成情况：
  pytest 85 passed（>= 83 ✓）/ ruff 全绿 ✓ / npm run test 29 用例退出码 0（>= 10 ✓）/
  npm run build 通过 ✓ / OrdersList/FinancialRecords 无手写分页去重 ✓
```

### 迭代执行日志（2026-09-10 深夜，会话 3——审查驱动的持续迭代）

```
起点：NIGHT 收尾（1193225），经用户确认继续，预算至电量 ~30%。
完成（按序，每项过对应门禁）：
  1. CI 前端 job 接入 vitest（aab9200）→ push → 三 job 绿（run 34498826571）。
  2. 双路审查（两个并行 agent）：后端 9 项发现（1×P1 / 3×P2 / 5×P3）+ 前端 11 项发现
     （1×P1 / 4×P2 / 6×P3）；全部逐条读码核实后采纳修复，剔除不成立项。
  3. 后端修复 ×7 commit（pytest 90 passed）：
     - [P1] 限流键取真实 IP：_client_ip 优先 X-Real-IP（nginx 无条件覆写、api 仅内网可达，
       头可信）；此前生产全站共享 web 容器 IP，10 次/分钟即被打满登录/注册。
     - [P3] 微信登录补限流（jscode2session 外呼配额防刷）。
     - [P2] 临期提醒按"本周期"去重：订单重开刷新 expired_at 后旧提醒不再压制新提醒
       （此前 republish 过的订单永远收不到第二次临期提醒）。
     - [P2] 拉黑接口限 tenant_admin：super_admin 无租户写入非空列必 500 → 守卫层 403。
     - [P2] PATCH 订单显式 null 过滤：非空列（lng/lat/grade_subject 等）按未提供处理，
       可空字段（备注/联系方式）保留置空能力。
     - [P3] 订单/流水 CSV 导出行数上限（20000/50000），防大租户 OOM。
     - [P3] GEO 空租户 120s 短 TTL 标记（独立 key，防 WRONGTYPE），空租户不再每请求全量查库。
     - [P3] 生产开启 AUTO_CREATE_SCHEMA 在配置加载即 RuntimeError（compose 已显式 false，兜底防误配）。
  4. 前端修复 ×4 commit（build + 29 用例绿）：
     - [P1] 路由守卫仅 401 才登出：地铁断网不再误清会话（fetchMe 失败不缓存，放行导航）；
       顺带修 super_admin 未登录访问 /owner/tenants 直达 owner 登录标签。
     - [P2] GET 重试排除 /auth/ 探活（守卫 await 场景避免切页延迟加倍）；
       并发 401 失效动作去重（3s 兜底复位）。
     - [P2] Board.vue：onBeforeUnmount 销毁地图（修复每次进板泄漏一份 AMap.Map）、
       刷新按钮失败 toast、城市地理编码竞态守卫（慢返回不拽回旧城市）。
     - [P2] OrdersList/ApplicationsReview 加载失败明确提示，不再误显示"暂无订单"。
  5. P2-6 资金审计日志 ×4 commit（pytest 94 passed + 本地迁移 round-trip + alembic check 无漂移）：
     - audit_logs 表（tenant/actor/action/object/ip/created_at，(tenant,created_at) 与
       (object_type,object_id) 双索引）+ 迁移 b2f6d8e4c1a9；
     - 五个资金写路径接入（confirm_deposit/confirm_balance/trial_failed/forfeit/cancel），
       审计写失败仅留日志不阻断资金主流程；不改既有响应；
     - 超管查询接口 GET /api/v1/audit-logs（tenant/action/日期过滤 + 分页，非法 action 422）；
     - 回归测试 tests/test_audit_logs.py。
  6. P3 文档：根 CONTEXT.md（词汇表/状态机/资金红线/硬约定/模块地图）+
     ADR-0001 状态机、ADR-0002 脱敏与解锁卡点、ADR-0003 Redis 降级、ADR-0004 naive UTC。
  7. P2-8：nginx 增加 Content-Security-Policy-Report-Only（AMap 域名白名单 + unsafe-inline
     过渡）与 /csp-report 上报端点，观察期一周后收紧强制。
  8. 审查补充修复：OWNER_TOKEN_VALID_AFTER——老板 token 无账号行可挂失效标记，
     以全局配置时间戳吊销存量 super_admin 会话（轮换访问码时同步更新）。
  9. P3 发布流程部分落地：compose 三服务补 image: 命名。
  10. P2-7 前置：ADR-0005 PII 静态加密草案（AES-256-GCM + key_version 轮换 + phone HMAC
      等值检索；明确以 P2-1 完成为实施前置）——草案待评审，未实施。
  11. push 21ed15d → CI 三 job 全绿（run 34503938975，MySQL job 验证新迁移）。
  12. 后台自查 agent 复查 aab9200..HEAD：3 项发现全部处置——
      a) [HIGH] record_audit 吞掉的 flush 失败会把会话置为 pending-rollback，调用方下一次
         flush 连带 500 + 业务全量回滚，违背"审计不阻断业务"约定 → 改为 begin_nested
         SAVEPOINT 隔离（25bc80b），新增能区分新旧实现的回归测试（注入 NOT NULL 违约，
         验证会话存活、失败审计行不落库）；
      b) [MEDIUM] Board 异步 onMounted 在 SDK 加载期间卸载，会在已卸载 DOM 上重建永不
         销毁的地图实例 → disposed 标记 + await 后短路（7b20289）；
      c) [LOW] 临期提醒"本周期"起点按 expired_at−有效期推算，管理端 PATCH 手工缩短有效期
         的路径可能漏发一次提醒 → 代码注释标注局限（42da0d7）；彻底修法（orders 加持久化
         重开时间戳列）列入遗留，需迁移+回归，不在夜间做。
      其余审计面（审计钩子时序、FastAPI 签名、时区口径、X-Real-IP 信任面、401 去重复位、
      迁移链、审计查询端点）全部核实无问题。
重要发现（对后续迭代有指导意义）：
  1. tests/ 文件按字母序收集，凡字母序在 test_business_features 之前的新测试文件，
     模块级 import config 触碰链（models.domain/services.auth）会把 settings 单例的
     OWNER_ACCESS_CODE 固化为 conftest 默认值，破坏 test_password_auth——已在新文件头
     注释声明该 footgun，相关 import 一律函数内。
  2. 限流按 IP 的 P1 缺陷说明：安全修复必须对照真实部署拓扑（nginx/compose）评估，
     不能只看代码逻辑。
  3. C 端注销（P2-7）不是纯增功能：改登录/注册唯一性语义（手机号 hash），必须白天有人盯。
最终基线：pytest 95 passed / ruff 绿 / 前端 29 用例 + build 绿 / CI 三 job 绿 / compose 校验过。
遗留（按优先级）：
  1. 临期提醒周期标记持久化（orders.expiry_refreshed_at 列 + 迁移），消除上面的 LOW 局限；
  2. 前端 api/*.ts 返回类型统一（authApi.me 等仍无类型）；
  3. formatMoney(null) 当前显示 ¥0.00（测试锁定），是否改"-"占位待产品定；
  4. CSP 观察一周后由 Report-Only 收紧为强制。
```

### 迭代补充日志（2026-09-11 晨，会话 4——清单清零 + P1-9）

```
完成：
  1. 问题清单 OPEN-ISSUES-2026-09-11.md 建档（8b689fe）并随进度更新（a3b53dc）。
  2. §1.1 临期提醒周期持久化（41c72c1）：orders.expiry_refreshed_at 列（迁移 d7e2b4a8f6c1，
     round-trip + drift check 验证）；refresh_order_expiry 收敛到 order_maintenance 单点
     （顺带消除 §5.2 双份定义）；PATCH 改 expired_at 同步打标——管理端缩短有效期不再漏发提醒；
     回归测试锁 PATCH 路径。基线 96 passed。
  3. §1.3 usePagedList 翻页死端（b3c7e47）：整页去重后零新增 → hasMore 终止，防后端分页
     异常导致无限空转；vitest 30 用例。
  4. P1-9 Sentry 接入（219686b）：sentry-sdk[fastapi]==2.69.1 + @sentry/vue==10.74.0（pin）；
     DSN 走 SENTRY_DSN / VITE_SENTRY_DSN 环境变量，未配置完全 no-op；后端 lifespan 与
     scheduler 独立容器入口均初始化（environment 按 DEV_MODE 区分，send_default_pii=False，
     采样 0.1）；前端挂在全局 errorHandler（captureException 仅在初始化后调用）；
     api/scheduler compose 透传 SENTRY_DSN；本地 .env / frontend/.env.local 已写入真实 DSN
     （两者均 git-ignored）。
  5. 顺带修复：.gitignore 的 .env.* 误伤了 **/.env.*.example 模板——两个生产部署样例
     （根 + frontend）首次入库。
  6. 第三轮审查（后台 agent：parser/批量导入/resumes/notifications/credit/推荐/教员视图）
     7 项发现全部处置：
     - [P2] AI 条目 raw_text 回退整批文本（跨单交叉泄露）→ 以所属段为原文（accf591）
     - [P2] 无头多单粘贴被轻量解析合并丢单 → _looks_like_multi_order 启发触发 AI 兜底（accf591）
     - [P2] 部分段 AI 失败静默 → BatchParseResponse.warnings 透出 + 前端提示（accf591）
     - [P3] null 科目 AttributeError → or 兜底（accf591）
     - [P3] lng/lat 越界致 GEOADD 静默失败 → 导入/更新 schema 加边界约束（accf591）
     - [P3] MyApplications 取消弹窗取消误报失败 → catch 分离（7713212）
     - 保留现状：batch-import 单行 422 中止整批（详情含 raw_id、UI 已预过滤；
       静默跳过会在资金导入中悄悄丢单，更差权衡）
  7. P2-5 降级方案（092773b）：超管 GET /api/v1/internal/stats——租户/教员/订单/投递/
     资金/审计六维聚合（含 24h 资金操作按 action/actor_role 计数，复用 audit_logs）；
     是否再接 Prometheus/instrumentator 仍开放（D5）。
  8. §5.1 前端 api 层类型全量统一（3e631d9）：全部函数泛型 + 显式返回类型；auth/order
     store 与 BatchImport/MapBoard 本地类型副本收敛到 api/types；OrderDetail 的教员视角
     状态描述句保留（有意设计，非漂移）。
  9. DEPLOY_CHECKLIST 补 SENTRY_DSN / VITE_SENTRY_DSN 两行。
  10. SIM105 清理复判为**跳过**：except 块内的降级注释承载文档，ruff 自动改写
      contextlib.suppress 会丢注释，需逐处手工搬——留给低风险白天时段。
  11. P2-3 Playwright E2E 冒烟落地（f04ae74）：`frontend/e2e/smoke.spec.ts` 三用例
      （健康检查/未登录橱窗/中介登录→工作台），playwright.config 自动拉起
      uvicorn（DEV_MODE 播种 tx886/dev123456，独立 e2e.db）+ vite dev；本地 3/3 绿，
      CI workflow_dispatch 首跑绿（57s）。不挂 push/PR，不挡常规 CI。
  12. E2E 首跑抓到 **P1 产品 bug** 并修复（dfd2c96）：TeacherTabbar 在公开橱窗页
      未登录也拉未读数 → 401 触发全局"登录已过期"跳转，游客直接被踢去登录页。
      修复：未登录跳过该拉取。
  13. 顺带修复本地旧库 500（b963156）：init_db 补 expiry_refreshed_at 回填
      （P2-1 双轨问题的现实案例——E2E 用本地旧 dev.db 时当场复现）。
  14. 依赖专项（E2E 兜底下升级，d02d02c/01efce3）：pinia 2.3.1→4.0.3、
      vue-router 4.6.4→5.3.1，每次升级过 vitest+build+E2E 三关；
      tailwind 4 与 TS 7/vue-tsc 3.3 需样式/类型肉眼回归，保留待专项。
  15. 掩码工具边界回归（tests/test_masking.py，6 用例）——ADR-0002 的脱敏底座。
门禁（本轮末）：pytest 106 passed / ruff 绿 / build + vitest 30 用例绿 / E2E 3 用例绿 / compose config 过。
Sentry 生效条件（部署侧）：服务器 .env 填 SENTRY_DSN（同本地值）；前端构建环境注入
VITE_SENTRY_DSN；部署后到 sentry.io 两个项目确认 Issues 列表能收到事件（可点一次"发送测试事件"）。
```

### 夜间会话 5 日志（2026-09-12 深夜，A1 + C1 + D4-B，用户拍板后执行）

```
用户拍板：D4 选 B——formatMoney 空值维持 ¥0.00。
完成：
  1. A1 E2E 扩链（9dd13f3）：frontend/e2e/teacher-flow.spec.ts 五用例串行全链——
     API 预置订单（batch-import 独立数据）→ UI 教员注册（tx886）→ Profile 建简历 →
     UI 投递（选择简历弹层 + 确认对话框）→ API 五步审核（shortlist/deposit/trial/
     balance/complete 逐断言）→ API 脱敏断言（教员视角 parent_phone/exact_address 为空、
     原文含掩码；B 端完整）→ UI"我的投递"显示已成交。调试三轮修掉测试自身三处
     （简历经历必填、确认对话框文案干扰断言、教员登录需邀请码）。
  2. C1 Board 拆分（P1-1 目标结构达成，Board.vue 1100 → 765 行）：
     - 4b488cd useAMap composable：地图生命周期/标记渲染/高亮/定位/销毁/卸载守卫内聚；
     - 151b79a CityPicker + AgentPicker 组件：弹层模板与表单状态内聚
       （AgentPicker 表单随 agents 长度变化自动收起；CityPicker 打开时重置搜索/省份）；
     - 4979d90 RecommendList + OrderSheet 组件：推荐抽屉（窗口轮换内聚，items 变化归零）
       与订单操作面板（v-model + view/apply 事件）。
     每步独立 commit，过 vue-tsc + vitest + 橱窗 E2E。
  3. D4 固化（7f6cda0）：format.ts 头注释记录决策与锁定测试位置。
门禁（夜跑末）：pytest 106 passed / ruff 绿 / build + vitest 30 用例绿 / E2E 8 用例绿。
验收提示（用户早晨）：Board 拆分后需人眼确认一次地图渲染/标记点击出面板/推荐卡点击
高亮定位/城市切换视角移动——E2E 已覆盖锚点但地图视觉需人工。
```

### 会话 6 日志（2026-09-13，C2 独立试跑——摸清真实前置后安全回滚）

```
背景：用户给 2 小时独立窗口跑 C2。完成前置工具与 dev.db 整备，核心切换触雷后按协议回滚。
完成：
  1. scripts/schema_diff.py 对账工具入库（c7c384a）：alembic compare_metadata 对任意
     目标库（MySQL/SQLite）做只读 diff，退出码可脚本判断。踩掉两个坑：
     a) async 驱动必须 create_async_engine + run_sync（同步引擎直接 MissingGreenlet）；
     b) 只 import database.Base 不导入 models.domain 时 metadata 为空，
        diff 会误报"remove 全部表"。
  2. dev.db 整备：备份（dev.db.backup-0913）+ 回填 4 个缺失索引
     （idx_app_order_status / idx_app_tenant_status / idx_status_expired / idx_notification_order，
      均为 create_all 时代 d5b9e7c3a1f2 之后迁移新增、_ensure 未覆盖的）+ alembic stamp head。
  3. 试跑 init_db → alembic 切换：全量回归暴露 table teachers already exists，
     定位出**硬前置**：7 个存量测试模块（business_features/financial_labels/order_guards/
     password_auth/production_guards/profile_contacts/roi_summary）在 import 时硬设
     os.environ["DATABASE_URL"]，但 settings 是单例——首个 import config 的模块冻结 URL 后，
     所有旧式模块的 init_db/create_all 实际共享同一个陈旧库文件。
     init_db 切 alembic 后：首个模块全链建表，后续模块全部 "table exists" 崩溃。
  4. 安全回滚：init_db 恢复 create_all + _ensure_*；conftest 恢复 init_db 调用
     （conftest 的 create_all 解耦本身还引入了跨文件 SQLite 锁干扰，一并回滚）。
  5. 保留成果：schema_diff.py 工具；dev.db 索引回填 + stamp（与恢复后流程兼容，
     且使 dev.db 从此可 `alembic upgrade head` 增量迁移）。
结论（C2 正式路径，全部写进 STATE.md）：
  ① 迁 7 个存量模块到 conftest（~2-3h，模式照抄 money_flow 迁移）；
  ② init_db 切 alembic（实现照抄本次试跑，含 asyncio.to_thread + 绝对 script_location）；
  ③ conftest 用 create_all 解耦（照抄本次 conftest diff）；
  ④ 全量回归 + CI MySQL job。
 MySQL 容器本地对账为可选加分项（镜像拉取受夜间网络影响两次中断，白天网络好时 5 分钟）。
门禁：pytest 106 passed / ruff 绿（回滚后全绿验证）。
```