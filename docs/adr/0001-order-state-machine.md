# ADR-0001: 订单状态机——投递流程驱动 + 通用 transit 白名单

- 状态：已采纳
- 日期：2026-09-06（成文 2026-09-10，追溯既有决策）
- 关联代码：`utils/state_machine.py`、`routers/v1/applications.py`、`models/domain.py::OrderStatus`

## 背景

订单的候选、定金、试课、成交各阶段早期各自占用一个订单状态（pending_deposit /
pending_approval / pending_balance），导致：状态枚举膨胀；一笔订单有多个候选时无法表达；
通用 `/orders/{id}/transit` 入口可被用于跳过资金流程任意改状态。

## 决策

1. 订单状态收敛为四个活跃值：`recruiting → trial_in_progress → completed`，外加 `archived`。
   候选/定金阶段不再占用订单状态——订单保持 `recruiting`，阶段信息在 `Application.status` 上。
2. 订单状态的推进由**投递流程**驱动（applications 路由的 confirm-deposit / start-trial /
   confirm-balance / complete），通用 `/transit`、`/archive`、`/batch-status` 只允许
   白名单内的跳转：`recruiting→archived`、`trial_in_progress→{completed,recruiting,archived}`。
3. 三个废弃状态仅保留枚举值兼容历史行，`ALLOWED_TRANSITIONS` 中它们无出边也无入边，
   任何写路径不得再产生。
4. 所有跳转必须过 `validate_transition(current, target, role)`：先状态白名单（ValueError），
   再角色权限（PermissionError）；teacher 角色不直接驱动订单状态。

## 后果

- 正向：一笔订单多候选可表达；资金流程不可被 transit 绕过；`tests/test_property_state_machine.py`
  以 property test 锁死"全域组合只抛 ValueError/PermissionError、废弃状态永不可达"。
- 代价：排查问题时需同时看订单状态与投递状态（订单状态是投递流程的派生结果）。
  教员重新付定金（试课失败后）依赖 `_settle_order_after_disposal` 的条件回退：
  仅当前试课教员被处置且回退安全时订单才回 `recruiting`，防止复活已完成/已归档订单。
