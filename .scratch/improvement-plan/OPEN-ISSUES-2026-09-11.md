# 待提升问题清单（2026-09-11 晨，第 2 次更新）

> 定位：截至 `b3c7e47` 的全部已知问题、局限、待决策项与改进队列。
> 上游台账：`PLAN.md`（原始方案+执行日志）、`STATE.md`（断点续跑状态）。
> 本文回答一个问题：**现在还有什么在提升，各自卡在哪，下一步是什么。**

---

## 0. 当前健康基线（问题清单的参照系）

| 维度 | 状态 |
|---|---|
| 后端测试 | pytest 96 passed（含 6 个 hypothesis property + 6 个加固/提醒回归 + 4 个审计回归） |
| Lint | ruff check 全绿（E501/SIM105/UP042 等按约定 ignore，见 §5.3） |
| 前端测试 | vitest 30 用例（4 文件）全绿 |
| 前端构建 | `npm run build`（vue-tsc strict）通过 |
| CI | 三 job 全绿：Backend / MySQL 迁移 round-trip / Frontend |
| 模型漂移 | `alembic check` SQLite 阻塞无漂移；MySQL 观察期 continue-on-error |
| 审计 | 双 agent 全库审查 20 项发现已处置 19 项，剩余 1 项见 §1.2（产品决策） |
| 文档 | CONTEXT.md + ADR-0001~0005 就位 |

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
| D5 | **P2-5 指标方案** | Prometheus + instrumentator（需 gate 生产暴露）vs 超管鉴权 `/internal/stats` 降级方案；另需决定是否投入 locust 压测基线 | 2~4h |
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
   另：前端工具链大版本升级（TypeScript 5.9→7、vue-tsc 2.2→3.3、pinia 2→4）此前
   Dependabot PR 因 CI 红被关闭，属**待专项升级**的既知债。
4. **发布演练**：compose 镜像名已补（smart-tutor/api:latest、smart-tutor/web:latest），
   下一次发版顺带验证 `docker compose build` 产物可推可拉。

---

## 5. 技术债小项（收益明确、随时可插队做）

1. **前端 api/*.ts 返回类型统一**：`authApi.me`、`ordersApi.batchParse`、`publicApi.getBoard`
   等仍是无类型 `Promise<any>`；统一为 `client.get<T>` 泛型 + 显式返回类型（审查发现 9，
   约 1h）。做完后 fetchMe 的 `res.role` 等访问才有编译期保护。
2. **~~`_refresh_order_expiry` 双份定义~~**：已随 §1.1 修复收敛到
   `services/order_maintenance.py::refresh_order_expiry` 单点（`41c72c1`）。
3. **ruff 遗留豁免**：E501（175 处长行，可跑一轮 ruff format 收敛）、SIM105（32 处
   try/except-pass）、UP042（4 处 StrEnum）均按当时决议 ignore；可在低风险时段逐项清零后
   从 ignore 列表摘除。
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
5. §5.1 前端 api 类型统一（1h，可穿插）
6. P2-7 注销流程细化 ADR → 实施（1 天，需盯回归）
7. P2-3 Playwright E2E（半天）
```

> 原 §1.1/§1.3 与 D1 均已完成；夜间可无人值守的清零——
> 其余全部卡决策、卡环境或红线禁区。
