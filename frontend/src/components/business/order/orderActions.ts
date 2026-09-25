/**
 * 订单可用操作的展示适配（Batch 02）：
 * 根据后端真实状态（OrderStatus + 我的投递状态）生成"展示什么操作"的视图模型。
 *
 * 架构红线（规格书）：
 * - 前端**不判断**操作是否合法——这里产出的只是展示配置；
 *   真正合法性由后端 403/409/422 把关，页面处理器必须处理这些错误；
 * - 不在此实现第二套状态机：只读 API 已有状态做展示映射；
 * - 一个页面原则上一个主要 CTA，次要操作降级展示。
 */
import type { ApplicationItem, OrderStatus } from "@/api/types";

export interface OrderActionViewModel {
  key: string;
  label: string;
  variant: "primary" | "secondary" | "ghost" | "danger" | "text";
}

export interface TeacherOrderActions {
  primary?: OrderActionViewModel;
  secondary: OrderActionViewModel[];
}

/** 教员侧有活跃投递的状态（与后端 409 口径一致：定金已付仍招聘中，不可重复投递） */
const ACTIVE_APPLICATION_STATUSES = new Set([
  "pending",
  "shortlisted",
  "deposit_paid",
  "trial_in_progress",
  "balance_paid",
  "completed",
]);

/** 页面分发约定：key → 现有处理器（apply 打开简历选择弹层，contact 复制投递消息，applications 跳我的投递） */
export type TeacherOrderActionKey = "apply" | "contact-agent" | "applications";

export function buildTeacherOrderActions(
  order: { status: OrderStatus },
  application: ApplicationItem | null | undefined,
): TeacherOrderActions {
  const hasActiveApplication =
    !!application && ACTIVE_APPLICATION_STATUSES.has(application.status);
  const secondary: OrderActionViewModel[] = [];

  if (order.status === "recruiting") {
    if (hasActiveApplication) {
      // 已投递：主 CTA 引导微信对接（真实业务为中介套中介，见 ADR-0007）
      return {
        primary: { key: "contact-agent", label: "复制消息 · 微信联系中介", variant: "primary" },
        secondary: [{ key: "applications", label: "查看我的投递", variant: "secondary" }],
      };
    }
    // 未投递（或历史投递已被拒/退，可重新投递）
    return {
      primary: { key: "apply", label: application ? "重新投递" : "选择简历并投递", variant: "primary" },
      secondary: application ? [{ key: "applications", label: "查看我的投递", variant: "secondary" }] : [],
    };
  }

  // 非招聘中：主操作引导查看投递进度，联系中介保留为次要操作
  if (hasActiveApplication) {
    secondary.push({ key: "contact-agent", label: "复制消息 · 微信联系中介", variant: "secondary" });
  }
  return {
    primary: { key: "applications", label: "查看我的投递", variant: "primary" },
    secondary,
  };
}

/* ────────────────────────────────────────────────────────────
   B 端（中介）操作视图模型（Batch 04）
   与 C 端共享 ViewModel 结构，但动作口径完全不同：
   重状态流转（审核/试课/资金确认）在 ApplicationsReview 工作流中，
   这里产出深链入口 + 直接订单动作（归档/重新发布，页面侧二次确认）。
   合法性仍由后端 403/409/422 把关。
   ──────────────────────────────────────────────────────────── */

export type AdminOrderActionKey =
  | "review"
  | "financial"
  | "archive"
  | "republish";

export interface AdminOrderActions {
  primary?: OrderActionViewModel;
  secondary: OrderActionViewModel[];
}

export function buildAdminOrderActions(order: { status: OrderStatus }): AdminOrderActions {
  if (order.status === "recruiting") {
    return {
      primary: { key: "review", label: "去审核投递", variant: "primary" },
      secondary: [{ key: "archive", label: "归档订单", variant: "secondary" }],
    };
  }
  if (order.status === "trial_in_progress") {
    return {
      primary: { key: "review", label: "处理试课结果", variant: "primary" },
      secondary: [{ key: "financial", label: "查看财务流水", variant: "secondary" }],
    };
  }
  if (order.status === "completed") {
    return {
      primary: { key: "financial", label: "查看财务流水", variant: "primary" },
      secondary: [],
    };
  }
  // archived
  return {
    primary: { key: "republish", label: "重新发布", variant: "primary" },
    secondary: [],
  };
}
