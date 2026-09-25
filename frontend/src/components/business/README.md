# 业务组件层（components/business）

Batch 01 预留、**Batch 02 正式落地**的业务 UI 基础层：围绕 Order Domain 组织的
展示组件与适配器。本层组件**禁止直接发请求**——数据由页面/容器层传入
（保持纯展示可测试）；状态口径只从 `api/types.ts` 与 `constants/orderStatus.ts`
读取，**严禁重定义状态、严禁前端计算金额/分数/权限**（后端是唯一业务真相来源）。

## 架构（Batch 02）

```
API Response (types.ts)
      ↓
Presentation Adapter（timeline.ts / recommendation.ts / order/orderActions.ts）
      ↓
UI Model（TimelineStep[] / RecommendationExplanation / OrderActionViewModel / FinancialRow[]）
      ↓
Business Components（OrderTimeline / RecommendationExplainCard / OrderFinancialSummary）
      ↓
页面（views/teacher/OrderDetail.vue —— Order Workspace）
```

## 组件与适配器

| 文件 | 职责 | 数据来源 |
|---|---|---|
| `OrderTimeline.vue` | 纯展示：渲染 `TimelineStep[]`（竖向时间线，done/current/todo/skipped 四态） | 上层传入 |
| `timeline.ts` | **两条状态机分层适配**：`buildOrderLifecycleSteps(order)`（订单生命周期，只由 OrderStatus 驱动）与 `buildApplicationLifecycleSteps(application)`（投递进度辅助层）。绝不把两条线混成一条 | `OrderStatus` / `ApplicationItem` |
| `recommendation.ts` | `buildRecommendationExplanation(item)`：score_breakdown 六维 + reasons 原文 → `RecommendationExplanation`；数据缺失返回 null（页面显示真实空态，不放假默认值） | `TeacherOrderRecommendationItem` |
| `RecommendationExplainCard.vue` | "为什么推荐给你？"：匹配度 + 六维分数条 + 后端 reasons 原文。解释能力而非 AI 炫技（ai 紫仅作 accent） | `RecommendationExplanation` |
| `OrderFinancialSummary.vue` | 资金状态行（定金/尾款/退款/没收 + 已付/待收/已退/已没收），金额/状态/时间全由 API 字段经页面适配传入，**组件内禁止出现金额计算** | `FinancialRow[]` |
| `order/orderActions.ts` | `buildTeacherOrderActions(order, application)`：按后端真实状态产出操作视图模型（一个主 CTA + 次要操作）。**只负责展示什么，不判断合法性**——后端 403/409/422 由页面处理器兜底 | `OrderStatus` / `ApplicationItem` |
| `ai/aiImport.ts` | AI Import 适配器（Batch 03）：`buildDraftViews(items)` → 字段级行（normal/warning/missing，⚠ 来自后端 `missing_fields` 口径与显式字段空值，**不编造**）+ 三级分诊（ready/review/blocked，集中于此，页面不做判断）；后端定性置信度 `parser_confidence`（high/medium/ai）只翻译等级，**绝不生成数值百分比** | `OrderDraftItem`（含 `parser_confidence`/`missing_fields`/`needs_manual_review`） |
| `ai/AIImportProgress.vue` | 解析进度/异常摘要 + 分诊过滤入口；解析中只有诚实文案，**无前端自跑的假百分比** | 分诊计数 + 后端 `warnings` 段失败数 |

## 已接入页面

- `views/teacher/OrderDetail.vue`（Order Workspace：Header+主操作 / 双层时间线 / 联系对接中介 / 订单信息 / 资金状态 / 409 刷新提示）
- `views/admin/BatchImport.vue`（AI Import Workspace：四步工作流 + 分诊摘要过滤 + 字段级校对 + 批量创建计数=可创建数）

## 规划中（Batch 03+ 按需实现）

| 组件 | 用途 | 数据来源 | 现状说明 |
|---|---|---|---|
| `TeacherOrderCard` | 教员端订单卡（推荐态含可展开推荐解释区） | 已实现于 `components/teacher/TeacherOrderCard.vue`，按验收意见不强行移动目录 | 已实现并接入解释卡 |
| `ApplicationCard` | 投递卡片 | 已实现于 `components/admin/ApplicationCard.vue` | 保持原位，视觉随 Token 统一 |
| `TeacherProfileCard` | 教员画像卡 | `TeacherSummary` + 信用聚合 | 待建 |
| `TodoCard` | 工作台待办卡 | Dashboard 经营提醒接口 | 待建 |
| `AIImportProgress` | AI 录单识别进度/置信度 | `BatchParseResponse`（置信度需后端字段） | 待建，置信度属 API 缺口 |
| `OrderFinancialSummary`（B 端版） | 可解释账本（含已确认收入口径） | B 端暂无独立订单详情页 | 属 Batch 04（中介工作台）范围 |
