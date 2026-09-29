import type { OrderStatus } from "@/api/types";
import { ORDER_STATUS_TONES } from "@/constants/statusTone";

/** 订单状态文案唯一口径（仪表盘与订单列表共用；后端加状态时此处同步）。
 *  "completed" 统一叫"已成交"——与投递状态口径及 Dashboard 统计卡一致。 */
export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  recruiting: "招聘中",
  trial_in_progress: "试课中",
  completed: "已成交",
  archived: "已归档",
};

/** 订单状态徽标配色（含 ring 描边）。
 *  配色真源在 constants/statusTone.ts —— 与投递状态共用同一套色阶，
 *  此处只做拼接，视图层不得再手写状态颜色。 */
export const ORDER_STATUS_COLORS: Record<OrderStatus, string> = Object.fromEntries(
  (Object.keys(ORDER_STATUS_TONES) as OrderStatus[]).map((status) => [
    status,
    `${ORDER_STATUS_TONES[status].chip} ${ORDER_STATUS_TONES[status].ring}`,
  ]),
) as Record<OrderStatus, string>;
