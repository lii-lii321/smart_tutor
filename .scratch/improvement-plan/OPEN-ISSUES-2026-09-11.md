# 待提升问题清单（2026-09-12 凌晨，最终版）

> 定位：截至本轮（E2E 落地 + 依赖专项 + 第三轮审查）的全部已知问题、局限、待决策项。
> 上游台账：`PLAN.md`、`STATE.md`。

---

## 0. 当前健康基线（问题清单的参照系）

| 维度 | 状态 |
|---|---|
| 后端测试 | pytest 101 passed（property/回归/审计/内部统计/掩码边界全覆盖） |
| Lint | ruff check 全绿（E501/SIM105/UP042 等按约定 ignore，见 §5.3） |
| 前端单测 | vitest 30 用例全绿；api 层类型全量统一（vue-tsc strict 无本地副本） |
| 前端构建 | `npm run build`（vue-tsc strict）通过 |
| E2E | Playwright 冒烟 3 用例（健康检查/橱窗/中介登录→工作台），本地 + CI 双绿；workflow_dispatch 手动触发 |
| CI | 三 job 全绿：Backend / MySQL 迁移 round-trip / Frontend |
| 依赖 | pinia 4.0.3、vue-router 5.3.1 已升级（E2E 验证）；tailwind 4 / TS 7 见 §4.3 |
| 模型漂移 | `alembic check` SQLite 阻塞无漂移；MySQL 观察期 continue-on-error |
| 审计 | 三轮审查累计 32 项发现，已处置 31 项；剩余 1 项见 §1.2（产品决策） |
| 文档 | CONTEXT.md + ADR-0001~0005 + DEPLOY_CHECKLIST（含 Sentry）就位 |

---

## 0.1 E2E 首跑战果（2026-09-12 凌晨，P2-3 落地）

- Playwright + chromium：`frontend/e2e/smoke.spec.ts` 三用例——健康检查 / 未登录橱窗渲染 /
  中介登录→工作台；`npm run test:e2e` 一键拉起 uvicorn（DEV_MODE 播种 tx886/dev123456）+ vite dev。
- CI：`.github/workflows/e2e.yml`，workflow_dispatch 手动触发不挡 PR，**首跑已绿（57s）**。
- 首跑即抓到并修复一个 **P1 产品 bug**：游客逛公开橱窗被 TeacherTabbar 的未读拉取 401
  触发"登录已过期"跳转，直接踢去登录页（`dfd2c96`——未登录跳过该拉取）。
- 顺带发现并修复：本地旧 dev.db 缺新列导致橱窗 500——init_db 补
  `expiry_refreshed_at` 回填（`b963156`，P2-1 双轨问题的现实案例）。
- 依赖专项（E2E 兜底下大胆升级）：**pinia 2.3.1→4.0.3**（`d02d02c`）、
  **vue-router 4.6.4→5.3.1**（`01efce3`）全部门禁绿；
  tailwind 4（构建管线迁移）与 TypeScript 7/vue-tsc 3.3 需肉眼验证样式与全量类型，保留待专项。
- 新开的 Dependabot PR（vue-router 5、tailwind 4）已被本记录覆盖/保留待决策，未合并。

---

## 0.2 第三轮审查处置记录（AI 解析链路 + 教员端，2026-09-11 晨）

7 项发现全部处置（`accf591` / `7713212`）：
- ✅ [P2] AI 条目 raw_text 回退整批文本（跨单交叉泄露）→ 以所属段为原文
- ✅ [P2] 无头多单粘贴被轻量解析合并丢单 → `_looks_like_multi_order` 启发触发 AI 兜底
- ✅ [P2] 部分段 AI 失败被静默吞掉 → `BatchParseResponse.warnings` 透出 + 前端提示
- ✅ [P3] AI 返回 null 科目触发 AttributeError → or 兜底
- ✅ [P3] lng/lat 无边界（越界坐标 GEOADD 静默失败上不了地图）→ 导入/更新 schema 加 ge/le 约束
- ✅ [P3] 取消投递弹窗取消误报"操作失败" → 弹窗 catch 分离
- 🔶 [P3] batch-import 单行 422 中止整批 → **保留现状**：详情已含 raw_id、UI 已预过滤，
  改为静默跳过会在资金相关导入中悄悄丢单，属更差权衡
- 附带：MyApplications 状态文案统一到 constants（rejected 文案 "未通过"→"已拒绝"）；
  OrderDetail 的状态**描述句**（"投递待审核"等）为教员视角有意设计，不并入标准文案

---

## 1. 已知缺陷与局限（未修，附理由与修法）

> 2026-09-11 晨更新：原 §1.1（临期提醒周期标记）与 §1.3（usePagedList 死循环守卫）
> 已修复——`41c72c1`（orders.expiry_refreshed_at 列 + 迁移 d7e2b4a8f6c1 + PATCH 打标 +
> `_refresh_order_expiry` 收敛到 order_maintenance 单点 + 回归测试）、`b3c7e47`
> （整页零新增终止翻页）。基线升至 pytest 96 passed / vitest 30 用例。

### 1.2 formatMoney(null) 显示 ¥0.00 而非占位符【LOW，产品决策】
- **现状**：`frontend/src/utils/format.ts` 对 null/undefined/"" 返回 `¥0.00`
  （有单测锁定该行为）。财务汇总里"无数据"与"确为 0"在展示上不可区分。
- **为什么没修**：语义变更影响全站金额展示口径，且现有测试已把它当作约定锁定；
  改不动代码，改的是产品语义。
- **修法**：若决定改，`formatMoney` 对 null/undefined/"" 返回 `"-"`（与 formatDateTime
  对齐），同步更新 `tests/format.spec.ts` 与消费方（`formatAmount` 会把 "-" slice 成 "-"，
  需逐一核对财务页三处）。
- **建议时机**：产品拍板后 30min。

### 1.3 ~~usePagedList 无 total 时「整页重复项」的病态边界~~【已修复，`b3c7e47`】

### 1.4 其他已核实、暂不动的低危项
| 项 | 位置 | 说明 | 状态 |
|---|---|---|---|
| 超管会话吊销靠手动配置 | config.py `OWNER_TOKEN_VALID_AFTER` | 机制已建；轮换 OWNER_ACCESS_CODE 时需同步设置该值，属运维操作项 | 文档化于 ADR/配置注释 |
| 进程内限流兜底阈值翻倍 | middleware/rate_limit.py | Redis 不可用退化为单进程计数，`--workers 2` 下实际阈值 ×2 | ADR-0003 已记录，接受 |
| 缓存击穿无互斥 | public.py 橱窗缓存 | 降级瞬间库压力突增，靠 30s TTL + 当前量级消化 | ADR-0003 已记录 |
| TimedRotatingFileHandler Windows 多进程轮转可能失败 | utils/logging_config.py | 生产为 Linux 容器，本地单进程，影响有限 | 接受 |
| errorHandler 的 toast 依赖 vant 运行时 | main.ts | 极早期异常（vant 未挂载）toast 不显示，console 仍有全栈 | 接受 |
| MySQL drift check 观察期 | ci.yml continue-on-error | 当前只剩方言差异不报错；需观察几轮后改为阻塞 | 见 §4.2 |

---

## 2. 待决策清单（卡在"需要人拍板"，不是卡在工时）

> 2026-09-11 晨更新：**D1 Sentry 已落地**（`219686b`）——前后端 SDK 接入、DSN 环境变量化
> （`SENTRY_DSN` / `VITE_SENTRY_DSN`，未配置时完全 no-op）、本地 .env 已写入真实 DSN。
> 生产服务器部署时在 `.env` 填同一后端 DSN、构建前端时注入 VITE_SENTRY_DSN 即生效；
> 上线后首次部署应到 Sentry 后台确认两项目各收到事件。

| # | 决策 | 背景 | 拍板后工时 |
|---|---|---|---|
| ~~D1~~ | ~~Sentry DSN~~ | 已完成（P1-9），见上 | — |
| D2 | **ADR-0005 PII 静态加密评审** | AES-256-GCM + key_version 轮换 + phone HMAC 等值检索的草案已写；需确认密钥管理方式与实施窗口；实施前置 = P2-1 完成 | 评审 0.5h，实施另计 1~2 天 |
| D3 | **CSP 收紧时机** | Report-Only 已上线，需观察一周 `/csp-report` 与 access log，无意外违规后把响应头改为强制 `Content-Security-Policy` | 30min |
| D4 | **formatMoney 空值语义**（§1.2） | 产品决定"无数据"如何展示 | 30min |
| D5 | **P2-5 指标增强** | ~~超管 `/internal/stats` 降级方案~~ 已实现（`092773b`，六维聚合）；剩余决策：是否接 Prometheus/instrumentator 与 locust 压测基线 | 2~4h |
| D6 | **notifications 游标分页 & 订单多字段搜索**（P3） | 都标注"产品确认交互后再做" | 待定 |

---

## 3. 计划内未实施大项（PLAN.md 台账剩余，按建议顺序）

### 3.1 P1-1 Board.vue 拆分【红线：必须独占会话 + 真机冒烟】
1081 行文件（本会话仅做了地图销毁/竞态等点状修复，未动结构）。目标结构、步骤、
风险（AMap 生命周期/热更新泄漏）PLAN.md B 节已写全。**谁来做**：白天独占会话，
每拆一个组件跑 build + 手动冒烟（地图渲染/推荐卡高亮/订单 sheet/城市中介切换）。

### 3.2 P2-1 database.py 双轨收敛【前置：能连 MySQL 对账】
~300 行 `_ensure_*` 补丁退役。步骤已固化（干净 MySQL 建基准 → scripts/schema_diff.py
对账 → diff 清零 → 删补丁 → DEV_MODE init_db 走 alembic → CI MySQL check 改阻塞）。
**完成后同时解锁**：ADR-0005 实施、MySQL drift check 转阻塞、`AUTO_CREATE_SCHEMA` 护栏的历史包袱。

### 3.3 P2-7 教员注销流程【合规刚需，动 auth 语义】
软删 + 手机号脱敏存档 + hash 防重复注册 + 投递/流水匿名化。**风险**：改登录/注册
唯一性判定，必须有人盯资金与登录全回归；建议先出该子项的细化 ADR（复用 ADR-0005 的格式）。

### 3.4 P2-3 Playwright E2E 冒烟
场景链已定（登录→橱窗→投递→shortlist→confirm-deposit），`workflow_dispatch` 手动触发
不挡 PR。需要装浏览器依赖 + 本地起 DEV_MODE 服务的验证窗口，约半天。

### 3.5 P3 其余
staging 环境（需服务器）、发布流程剩余（semver tag + git-cliff CHANGELOG 自动化；
image: 命名已就位）、托管数据库（成本决策）、时区 tz-aware 迁移预案（ADR-0004 未决节）。

---

## 4. 观察期 / 运维跟进项（不需要写代码，需要有人看）

1. **CSP 违规报告**：上线后第 3、7 天各看一次 nginx access log 中 `POST /csp-report`
   与 4xx 特征，确认 AMap/Vant 白名单无遗漏 → 执行 D3。
2. **MySQL drift check**：连续几轮 CI 无输出差异后，把 ci.yml 的
   `continue-on-error: true` 摘掉改阻塞（P0-4 约定的两周观察期）。
3. **依赖审计**：CI 中 pip-audit / npm audit 为记录用步骤，出现高危时需人工升级；
   前端依赖专项现状：pinia 4 / vue-router 5 已升级（E2E 验证）；剩余 tailwindcss 4
   （构建管线迁移 + 样式肉眼回归）与 TypeScript 7 / vue-tsc 3.3（类型门禁本身升级）
   需有人盯，仍待专项。
4. **发布演练**：compose 镜像名已补（smart-tutor/api:latest、smart-tutor/web:latest），
   下一次发版顺带验证 `docker compose build` 产物可推可拉。

---

## 5. 技术债小项（收益明确、随时可插队做）

1. **~~前端 api/*.ts 返回类型统一~~**：已完成（`3e631d9`）——全部函数 `client.get<T>` 泛型 +
   显式返回类型；auth/order store 与 BatchImport/MapBoard 的本地类型副本收敛到 api/types
   单点（`TeacherInfo`/`TenantBrief`/`OrderBrief`/`ParsedOrderItem` 以别名兼容保留导出）。
2. **~~`_refresh_order_expiry` 双份定义~~**：已随 §1.1 修复收敛到
   `services/order_maintenance.py::refresh_order_expiry` 单点（`41c72c1`）。
3. **ruff 遗留豁免**：E501（175 处长行，可跑一轮 ruff format 收敛）、SIM105（32 处
   try/except-pass）、UP042（4 处 StrEnum）均按当时决议 ignore；可在低风险时段逐项清零后
   从 ignore 列表摘除。**注意**：SIM105 自动改写会丢 except 块内的降级说明注释
   （Redis 降级等注释是承载文档的），清理时须逐处手工搬注释，不能盲跑 --fix。
4. **tests 字母序 settings 单例 footgun**：字母序在 test_business_features 之前的新测试
   文件禁止模块级 import config 触碰链（test_audit_logs.py 头部有注释声明）。长期解法是
   conftest 统一 OWNER_ACCESS_CODE 并让存量文件改用 conftest 值（需逐文件核对断言）。
5. **notifications 游标分页**：现仅 `limit`（上限 100）无翻页，量大后"加载更多"做不了
   （已在 D6，等产品确认交互）。

---

## 6. 建议的下一轮迭代顺序（有人值守白天会话）

```
1. D1 ✅ Sentry 已完成（219686b）——上线部署后到后台确认收到事件即可
2. P1-1 Board.vue 拆分（独占会话 3~4h，真机冒烟）       ← 结构债大头
3. D3 CSP 收紧（若观察期已满且无违规，30min）
4. P2-1 database.py 收敛（需 MySQL 环境，半天~1 天）     ← 解锁 ADR-0005 与 MySQL check 阻塞
5. P2-7 注销流程细化 ADR → 实施（1 天，需盯回归）
6. P2-3 Playwright E2E（半天）
```

> 已完成：§1.1/§1.3、D1 Sentry、P2-5 降级方案（/internal/stats）、§5.1 前端类型统一、
> 第三轮审查 7 项。夜间可无人值守的清零——其余全部卡决策、卡环境或红线禁区。
