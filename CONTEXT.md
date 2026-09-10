# CONTEXT.md —— Smart Tutor 领域上下文

> 面向工程师/Agent 的单上下文领域文档。改动业务逻辑前先读这里；
> 架构决策见 `docs/adr/`，改进项台账见 `.scratch/improvement-plan/PLAN.md`。

## 产品一句话

家教中介的订单撮合平台：中介（B 端）录入家长订单并审核教员投递，教员（C 端）在地图橱窗
找单投递，成交后平台按信息费（定金 + 尾款）收费。

## 核心概念（词汇表）

| 术语 | 英文/代码标识 | 定义 |
|---|---|---|
| 租户 / 中介 | `Tenant`, tenant_admin | 使用平台的家教中介机构。登录凭邀请码 + 密码。数据按 `tenant_id` 强隔离 |
| 老板 / 平台 | super_admin | 平台方（owner-login，仅一个访问码），管理租户、全局封禁教员 |
| 教员 | `Teacher`, teacher | C 端求职大学生。微信 openid 或手机号+密码登录 |
| 订单 | `Order` | 家长需求单。`raw_id` 展示编号、`base_price` 单次课酬、`expired_at` 过期时间。状态见下 |
| 投递 | `Application` | 教员对订单的求职申请。订单状态实际由投递流程驱动 |
| 橱窗 | agent board | 教员端地图选单页（`/teacher/board/:inviteCode`），Redis GEO 索引 + 30s 响应缓存 |
| 候选队列 | shortlisted | 中介确认候选（未付定金），多人可同时排队 |
| 信息费 | info fee | 平台收入 = 定金 100 元锁定 + 尾款。`services/calculator.py` 唯一计算口径（**只读红线**） |
| 试课 | trial | 定金确认后开始试课（解锁家长联系方式），尾款确认后可标记成交 |
| 没收 | forfeit | 教员违约时已交信息费转为平台收入（`forfeited` 独立终态） |

## 订单状态机（唯一事实来源）

```
recruiting（招聘中）→ [教员付定金，订单保持 recruiting]
trial_in_progress（试课中）→ completed（成交）
任意活跃状态 → archived（归档）
trial_in_progress --试课失败/取消/没收（仅当前试课教员）--> recruiting
```

- 白名单与角色权限：`utils/state_machine.py`（`/orders/{id}/transit`、batch-status、archive 走它）；
- 业务状态流转（候选/定金/试课/成交）由 `routers/v1/applications.py` 驱动，不走通用 transit；
- `pending_deposit / pending_approval / pending_balance` 为废弃状态，只读兼容历史行，任何写入路径都不得产生。

## 资金流（红线区）

- 唯一计算口径 `services/calculator.py`：Decimal HALF_UP 两位小数；`base_price<=0` 或总额 < 定金 100 必拒；
- 流水表 `financial_records`（含 `operator_role`）；审计表 `audit_logs` 记录"谁、何时、哪个 IP"（超管可查 `GET /api/v1/audit-logs`）；
- 退款封顶实收金额（`min(refund, paid)`）；零退款也必须留没收流水，保证台账闭环；
- 写路径全部 `with_for_update()` 锁订单行，防并发资金穿透。

## 硬约定（改代码前必读）

1. **时间**：全库 naive UTC。MySQL 会话 `SET time_zone='+00:00'`，比较/筛选用 UTC 口径
   （见 ADR-0004；`middleware/auth.py` 有历史踩坑注释）。
2. **租户隔离**：新端点必须过 `assert_tenant_scope` / `tenant_scoped` / `require_tenant_owner`
   （`middleware/auth.py`），语义保持 404 防探测。
3. **脱敏**：教员视角永不返回 `parent_phone`/`exact_address`，`raw_text` 掩码；
   家长联系方式仅试课中经 `address-unlock` 解锁（见 ADR-0002）。
4. **Redis 可降级**：限流/橱窗缓存/GEO 全部允许 Redis 缺席，降级路径静默 + 日志（见 ADR-0003）。
5. **schema 双轨现状**：`database.py` 的 `_ensure_*` 补丁与 alembic 并存（P2-1 待退役）；
   改模型必须同步出 alembic 迁移（CI `alembic check` 阻塞）。
6. **DEV_MODE**：本地专有，会开种子数据与 dev-login；生产 `AUTO_CREATE_SCHEMA=true` 直接启动失败。
7. **API 契约**：只加不改；响应统一 `response_model`，错误文案由 `getApiErrorMessage`（前端）解析 FastAPI `detail`。

## 模块地图

```
main.py                  FastAPI 入口（lifespan：日志/建表/调度开关）
routers/v1/              API 面：orders, applications, auth, tenants, financial_records,
                         notifications, resumes, recommendations, public, audit_logs
services/                业务逻辑：calculator(只读), parser(DeepSeek 解析), recommendation,
                         geo(Redis GEO), order_maintenance(过期归档/临期提醒/Redis 客户端),
                         scheduler(独立容器循环), serializers(订单序列化单点), audit
middleware/              auth(JWT/角色/租户守卫), rate_limit(Redis 限流，进程内兜底)
models/domain.py         SQLAlchemy 模型 + 枚举（状态机唯一事实源）
models/schemas.py        Pydantic 请求/响应契约
alembic/versions/        迁移链（head 见 CI migration round-trip job）
frontend/src/            Vue3+Vant4：views/{teacher,admin}, api/(axios 封装),
                         stores/auth(pinia), composables/usePagedList, constants/
deploy/nginx.conf        唯一入口（80），设置 X-Real-IP；安全头见 P0-5
```

## 测试

- 后端：`pytest tests/ -q`（conftest 提供每用例独立 SQLite + `client` fixture + make_* 造数工厂；
  新测试直接用 fixture，不要再手写临时库样板）；
- 前端：`cd frontend && npm run test -- --run`（vitest + happy-dom，纯逻辑测试放 `frontend/tests/`）；
- 门禁：后端改动过 pytest + `ruff check .`；前端改动过 `npm run build`（含 vue-tsc）。
