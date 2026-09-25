/**
 * 订单生命周期时间线的展示适配（Batch 02：按验收反馈拆分两条状态机）。
 *
 * 架构红线（ChatGPT Batch 01 验收意见）：
 * - Order Status（订单生命周期：这单处于什么阶段）与 Application Status
 *   （投递生命周期：某教员的申请处于什么阶段）是**两个维度**，绝不合并成一条线；
 * - 本文件只是 Presentation Adapter：API 状态 → 展示步骤（label/state/time），
 *   不判断订单能否进入下一阶段、不执行业务操作——业务真相始终在后端。
 *
 * 步骤模型与页面解耦：OrderTimeline.vue 只渲染 TimelineStep[]。
 */
import type { ApplicationItem, OrderStatus } from "@/api/types";
import { ORDER_STATUS_LABELS } from "@/constants/orderStatus";
import { formatDateTime } from "@/utils/format";

export type TimelineStepState = "done" | "current" | "todo" | "skipped";

export interface TimelineStep {
  label: string;
  state: TimelineStepState;
  /** 已格式化的展示时间；todo 态通常为空 */
  time?: string;
  note?: string;
}

/* ────────────────────────────────────────────────────────────
   第一层：订单生命周期（只由 OrderStatus 驱动）
   阶段口径：创建 → 招聘中 → 确定教员 → 试课 → 成交 →（归档）
   以 constants/orderStatus.ts 的订单状态为准，不新增后端不存在的状态。
   ──────────────────────────────────────────────────────────── */

/** 订单状态在生命周期序列中的下标（archived 视为成交后的终态附加步） */
const ORDER_STAGE_INDEX: Record<OrderStatus, number> = {
  recruiting: 1,
  trial_in_progress: 3,
  completed: 4,
  archived: 4,
};

export function buildOrderLifecycleSteps(order: {
  status: OrderStatus;
  created_at: string | null;
}): TimelineStep[] {
  const currentIndex = ORDER_STAGE_INDEX[order.status];
  const labels = ["订单创建", "招聘中", "确定教员", "试课", "成交"];
  const steps: TimelineStep[] = labels.map((label, index) => {
    let state: TimelineStepState;
    if (index < currentIndex) {
      state = "done";
    } else if (index === currentIndex) {
      // 归档时订单已走完成交，全部步骤显示为完成
      state = order.status === "archived" ? "done" : "current";
    } else {
      state = "todo";
    }
    const step: TimelineStep = { label, state };
    if (index === 0 && order.created_at) {
      step.time = formatDateTime(order.created_at);
    }
    return step;
  });

  if (order.status === "archived") {
    steps.push({ label: "已归档", state: "current", note: "订单不在橱窗展示" });
  }
  return steps;
}

/* ────────────────────────────────────────────────────────────
   第二层：投递生命周期（某教员的申请进度，辅助信息）
   以 ApplicationItem 的状态与事件时间戳为准；缺时间戳的阶段
   只表达"是否已发生"，不伪造时间。
   ──────────────────────────────────────────────────────────── */

export function buildApplicationLifecycleSteps(application: ApplicationItem): TimelineStep[] {
  const status = application.status;

  const submitted: TimelineStep = { label: "已提交投递", state: "done", time: fmt(application.applied_at) };

  const shortlisted = ["shortlisted", "trial_in_progress", "balance_paid", "completed"].includes(status);
  const review: TimelineStep = {
    label: "中介审核",
    state: status === "rejected" ? "skipped" : shortlisted ? "done" : "current",
    time: fmt(application.shortlisted_at),
    note: status === "rejected" ? "未入选" : undefined,
  };

  const deposited = ["trial_in_progress", "balance_paid", "completed"].includes(status);
  const deposit: TimelineStep = {
    label: "定金",
    state: status === "refunded" ? "skipped" : deposited ? "done" : "todo",
    time: fmt(application.deposit_paid_at),
    note: status === "refunded" ? "定金已退还" : undefined,
  };

  const trialing = ["trial_in_progress", "balance_paid", "completed"].includes(status);
  const trial: TimelineStep = { label: "试课", state: stepState(trialing) };

  const paidOff = ["balance_paid", "completed"].includes(status);
  const balance: TimelineStep = { label: "尾款", state: stepState(paidOff), time: fmt(application.balance_paid_at) };

  const deal: TimelineStep = { label: "成交", state: stepState(status === "completed") };

  return [submitted, review, deposit, trial, balance, deal];
}

/** 订单状态的一句话展示口径（Badge 已有 AppStatusBadge，这里供时间线标题等场景复用） */
export function orderStatusLabel(status: OrderStatus): string {
  return ORDER_STATUS_LABELS[status];
}

function stepState(isDone: boolean): TimelineStepState {
  return isDone ? "done" : "todo";
}

function fmt(iso: string | null | undefined): string | undefined {
  return iso ? formatDateTime(iso) : undefined;
}
