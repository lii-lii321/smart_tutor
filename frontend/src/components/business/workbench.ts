/**
 * Workbench 适配器（Batch 04）：
 * Dashboard 已加载的真实 API 数据 → 待办/摘要视图模型。
 * 页面不做业务判断；**没有后端来源的指标就不产出**（不 mock、不估算）。
 */
import type { TodoViewModel } from "@/components/business/TodoCard.vue";

export interface WorkbenchInput {
  /** 订单状态计数（listOrders total，真实后端口径） */
  recruiting: number;
  trial: number;
  /** 待处理投递总数（applicationsApi.summary().total_applications） */
  applicationTotal: number;
}

/**
 * 异常口径说明：本产品已有的"急单"规则在 ApplicationsReview 的紧迫度标记
 * （一周没反应/临期，2026-09 产品拍板），属既有业务事实而非本批新造规则；
 * Workbench 摘要层暂不重复该计算，异常入口 = 待办中的 warning 项。
 *
 * 未读消息不进工作台：它属全局 chrome，已由 AdminShell 顶栏铃铛 + 角标承担，
 * 且"新投递"场景与「待审核投递」重复。工作台只留需要中介动手处理的三件事。
 *
 * ⚠️ 现状：本适配器目前无引用点。Dashboard 的行动队列改为直接读
 * summary.last_application_at 算 SLA 临期提示（比这里的静态文案更有用），
 * 本文件与 TodoCard.vue 作为通用待办组件保留备用。新增待办类视图时优先复用。
 */
export function buildWorkbenchTodos(input: WorkbenchInput): TodoViewModel[] {
  return [
    {
      key: "recruiting",
      title: "招聘中的订单",
      description: "为这些订单挑选并邀约合适教员",
      count: input.recruiting,
      status: "normal",
      actionLabel: "去处理",
    },
    {
      key: "trial",
      title: "试课中的订单",
      description: "跟进试课反馈，推进定金与成交",
      count: input.trial,
      status: "normal",
      actionLabel: "去跟进",
    },
    {
      key: "applications",
      title: "待审核投递",
      description: "教员等待审核结果，拖延易流失",
      count: input.applicationTotal,
      status: input.applicationTotal > 0 ? "warning" : "normal",
      actionLabel: "去审核",
    },
  ];
}
