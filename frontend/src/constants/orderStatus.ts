import type { OrderStatus } from "@/api/types";

/** 订单状态文案唯一口径（仪表盘与订单列表共用；后端加状态时此处同步）。
 *  "completed" 统一叫"已成交"——与投递状态口径及 Dashboard 统计卡一致。 */
export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  recruiting: "招聘中",
  trial_in_progress: "试课中",
  completed: "已成交",
  archived: "已归档",
};

/** 订单状态徽标配色（含 ring 描边，订单列表与仪表盘共用） */
export const ORDER_STATUS_COLORS: Record<OrderStatus, string> = {
  recruiting: "bg-slate-100 text-slate-600 ring-slate-100",
  trial_in_progress: "bg-violet-50 text-violet-600 ring-violet-100",
  completed: "bg-emerald-50 text-emerald-600 ring-emerald-100",
  archived: "bg-slate-100 text-slate-500 ring-slate-200",
};
