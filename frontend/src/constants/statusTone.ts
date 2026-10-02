import type { ApplicationStatus, OrderStatus } from "@/api/types";

/** 状态徽标配色的唯一出口。
 *
 *  投递状态与订单状态共用同一套语义色阶，任何视图都不得再手写状态颜色。
 *  历史上两者各写各的，导致同一状态跨页面颜色不一致：
 *    - deposit_paid 在我的投递是 sky、在订单详情是 cyan
 *    - trial_in_progress 在订单状态是 violet、在投递状态是 emerald
 *
 *  色相只有 4 族（info / success / warning / danger）+ 中性灰，
 *  程度差异用档位表达，档位职责与 WCAG 实测见 design-tokens.css。
 *
 *  配色约定：soft | mid 作底一律配 deep 文字（唯一达标组合）；
 *  deep 作底配白字。DEFAULT 档不做文字色，对比度不足。
 */
export type StatusTone = {
  /** 常规徽标：背景 + 文字 */
  chip: string;
  /** 描边徽标追加的 ring 色（AppStatusBadge 这类带 ring-1 的徽标使用） */
  ring: string;
  /** 终态达成的实心徽标；缺省表示与 chip 同款 */
  solid?: string;
};

const NEUTRAL: StatusTone = {
  chip: "bg-surface-soft text-muted",
  ring: "ring-default",
};

/** 投递状态配色。progress 三档递进是刻意设计：
 *  定金已付(浅) → 尾款已付(中) → 已成交(实心)，一眼看出推进程度。 */
export const APPLICATION_STATUS_TONES: Record<ApplicationStatus, StatusTone> = {
  pending: { chip: "bg-info-soft text-info-deep", ring: "ring-info-mid" },
  shortlisted: NEUTRAL,
  trial_in_progress: { chip: "bg-accent-soft text-accent-ink", ring: "ring-accent" },
  deposit_paid: { chip: "bg-success-soft text-success-deep", ring: "ring-success-mid" },
  balance_paid: { chip: "bg-success-mid text-success-deep", ring: "ring-success" },
  completed: {
    chip: "bg-success-mid text-success-deep",
    ring: "ring-success",
    solid: "bg-success-deep text-white",
  },
  refunded: { chip: "bg-warning-soft text-warning-deep", ring: "ring-warning-mid" },
  rejected: { chip: "bg-danger-soft text-danger-deep", ring: "ring-danger-mid" },
  forfeited: { chip: "bg-danger-mid text-danger-deep", ring: "ring-danger" },
};

/** 订单状态配色。与投递同名状态同色（trial_in_progress / completed 口径一致）。 */
export const ORDER_STATUS_TONES: Record<OrderStatus, StatusTone> = {
  recruiting: { chip: "bg-info-soft text-info-deep", ring: "ring-info-mid" },
  trial_in_progress: { chip: "bg-accent-soft text-accent-ink", ring: "ring-accent" },
  completed: {
    chip: "bg-success-mid text-success-deep",
    ring: "ring-success",
    solid: "bg-success-deep text-white",
  },
  archived: { chip: "bg-surface-soft text-muted", ring: "ring-default" },
};

export function applicationTone(status: string): StatusTone {
  return (
    APPLICATION_STATUS_TONES[status as ApplicationStatus] ?? {
      chip: "bg-surface-soft text-muted",
      ring: "ring-default",
    }
  );
}

export function orderTone(status: string): StatusTone {
  return (
    ORDER_STATUS_TONES[status as OrderStatus] ?? {
      chip: "bg-surface-soft text-muted",
      ring: "ring-default",
    }
  );
}
