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
  /** B 端未读消息数（notificationsApi.tenantUnreadCount） */
  notifUnread: number;
}

/**
 * 异常口径说明：本产品已有的"急单"规则在 ApplicationsReview 的紧迫度标记
 * （一周没反应/临期，2026-09 产品拍板），属既有业务事实而非本批新造规则；
 * Workbench 摘要层暂不重复该计算，异常入口 = 待办中的 warning 项。
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
    {
      key: "notifications",
      title: "未读消息",
      description: "新投递、订单临期都会在这里提醒",
      count: input.notifUnread,
      status: input.notifUnread > 0 ? "warning" : "normal",
      actionLabel: "查看",
    },
  ];
}
