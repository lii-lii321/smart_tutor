import type { ApplicationStatus } from "@/api/types";

/** 投递状态文案唯一口径（审核页与详情弹窗共用；后端加状态时此处同步） */
export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  pending: "待审核",
  shortlisted: "候选排队",
  trial_in_progress: "正在试课",
  deposit_paid: "定金已付",
  balance_paid: "尾款已付",
  completed: "已成交",
  rejected: "已拒绝",
  refunded: "已退款",
  forfeited: "定金已没收",
};
