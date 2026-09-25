/**
 * 订单生命周期时间线的数据构造（Batch 01：仅组件基础结构，业务页面 Batch 02+ 接入）。
 *
 * 步骤模型刻意与具体页面解耦：OrderTimeline.vue 只渲染 TimelineStep 数组，
 * 状态→步骤的映射统一在这里做，未来改状态机只需要改这一处（规格书要求：
 * 不要让前端"猜状态"，状态口径单点收敛）。
 */
import type { ApplicationItem, ApplicationStatus, OrderStatus } from "@/api/types";
import { formatDateTime } from "@/utils/format";

export type TimelineStepState = "done" | "current" | "todo" | "skipped";

export interface TimelineStep {
  label: string;
  state: TimelineStepState;
  /** ISO 或已格式化时间字符串；todo 态通常为空 */
  time?: string;
  note?: string;
}

const APPLICATION_DONE_STATES: ReadonlySet<ApplicationStatus> = new Set([
  "shortlisted",
  "trial_in_progress",
  "balance_paid",
  "completed",
]);

/**
 * 从订单状态 + 该订单上"我的投递"构造生命周期步骤。
 * 无投递时（教员浏览橱窗阶段）只有 创建→投递 两步；有投递时按投递状态机展开。
 * 请求方（Batch 02 的订单详情页）负责提供数据，本函数不做任何请求。
 */
export function buildOrderTimeline(
  order: { status: OrderStatus; created_at: string | null },
  application?: ApplicationItem | null,
): TimelineStep[] {
  const appStatus = application?.status;
  const steps: TimelineStep[] = [
    { label: "订单创建", state: "done", time: fmt(order.created_at) },
  ];

  const applied = appStatus !== undefined && appStatus !== "rejected";
  steps.push({
    label: application ? "教员投递" : "等待投递",
    state: stepState(applied, appStatus === "rejected"),
    time: fmt(application?.applied_at),
    note: appStatus === "rejected" ? "投递未通过" : undefined,
  });

  if (!application) {
    return steps;
  }

  const shortlisted = appStatus ? APPLICATION_DONE_STATES.has(appStatus) : false;
  steps.push({
    label: "中介审核",
    state: stepState(shortlisted, appStatus === "rejected"),
    time: fmt(application.shortlisted_at),
    note: appStatus === "rejected" ? "未入选" : undefined,
  });

  const deposited = ["trial_in_progress", "balance_paid", "completed"].includes(appStatus ?? "");
  steps.push({
    label: "定金确认",
    state: stepState(deposited, appStatus === "refunded"),
    time: fmt(application.deposit_paid_at),
    note: appStatus === "refunded" ? "定金已退还" : undefined,
  });

  const trialing = ["trial_in_progress", "balance_paid", "completed"].includes(appStatus ?? "");
  steps.push({
    label: "试课",
    state: stepState(trialing),
    time: undefined,
  });

  const completed = appStatus === "completed";
  // 成交时刻暂无独立时间戳字段（尾款时间最接近），Batch 02 接入时如需精确时间由后端补充
  steps.push({
    label: "成交",
    state: stepState(completed),
  });

  if (order.status === "archived") {
    steps.push({ label: "归档", state: "done" });
  }
  return steps;
}

function stepState(isDone: boolean, isSkipped = false): TimelineStepState {
  if (isSkipped) return "skipped";
  return isDone ? "done" : "todo";
}

function fmt(iso: string | null | undefined): string | undefined {
  return iso ? formatDateTime(iso) : undefined;
}
