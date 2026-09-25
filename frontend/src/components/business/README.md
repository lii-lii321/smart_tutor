# 业务组件层（components/business）

Batch 01 按《Smart Tutor 产品化重构》规格书预留的业务 UI 基础层。
本阶段只定义结构与"订单域 UI"的种子组件，**不改动任何业务页面**；
页面接入在 Batch 02（订单核心）进行。

## 已落地

| 组件 | 说明 | 数据来源 |
|---|---|---|
| `OrderTimeline.vue` | 订单生命周期时间线（创建→投递→审核→定金→试课→成交→归档），纯展示：渲染 `TimelineStep[]` | `timeline.ts::buildOrderTimeline(order, application)` |
| `timeline.ts` | 状态→步骤的映射单点：订单状态机/投递状态机口径变化只改这里；`buildOrderTimeline` 纯函数无请求副作用 | `api/types.ts` 的 `OrderStatus`/`ApplicationStatus`（不重新定义状态） |

## 规划中（Batch 02+ 按需实现，先占位防重复造轮子）

| 组件 | 用途 | 数据来源 | 现状说明 |
|---|---|---|---|
| `TeacherOrderCard` | 教员端订单卡（推荐态/公共态） | 已存在于 `components/teacher/TeacherOrderCard.vue`，Batch 02 统一收编到本层 | 已实现，暂留原位避免页面改动 |
| `ApplicationCard` | 投递卡片 | 已存在于 `components/admin/ApplicationCard.vue`，同上 | 已实现 |
| `TeacherProfileCard` | 教员画像卡（成绩单/投递列表复用） | `TeacherSummary` + 信用聚合 | 待建 |
| `TodoCard` | 工作台待办卡 | Dashboard 经营提醒接口 | 待建 |
| `AIImportProgress` | AI 录单识别进度/置信度展示 | `BatchParseResponse`（置信度需后端字段，属 Batch 03+） | 待建 |
| `OrderFinancialSummary` | 可解释账本（定金/尾款/退款/没收分项 + 时间线） | `FinancialRecordItem` by order | 待建 |

## 规则

- 本层组件**禁止**直接发请求：数据由页面/容器层传入（保持纯展示可测试）。
- 状态口径只从 `constants/orderStatus.ts` 与 `api/types.ts` 读取，严禁重定义。
- 视觉只消费 Design Token 语义类（brand/surface/primary/secondary/muted/default...），
  禁止裸写 slate-*/emerald-*。
