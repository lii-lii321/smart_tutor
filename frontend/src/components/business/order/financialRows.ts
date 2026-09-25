/**
 * 订单财务行适配器（Batch 04 自 C 端 OrderDetail 提取共享）：
 * C 端（我的投递）与 B 端（订单工作区）共用同一套资金状态行映射——
 * 金额优先取定金确认后的快照 app.fee（后端口径），缺失回退订单费用结构字段；
 * 状态只读投递状态，**前端不复算任何金额**（架构红线）。
 */
import type { ApplicationItem } from "@/api/types";

/** 订单资金状态行（OrderFinancialSummary 的渲染模型；定义在此供 C/B 两端共享） */
export interface FinancialRow {
  key: string;
  label: string;
  amount: string;
  state: "paid" | "pending" | "refunded" | "forfeited";
  /** 该笔资金事件的时间（API 有才传，不伪造） */
  time?: string;
}

function fmtTime(iso: string | null | undefined, formatDateTime: (v: string) => string): string | undefined {
  return iso ? formatDateTime(iso) : undefined;
}

export function buildOrderFinancialRows(
  order: { needs_manual_price: boolean; deposit_amount: number; balance_amount: number },
  application: ApplicationItem | null | undefined,
  formatDateTime: (v: string) => string,
): FinancialRow[] {
  if (order.needs_manual_price) return [];
  const status = application?.status;
  const depositAmount = application?.fee?.deposit ?? order.deposit_amount;
  const balanceAmount = application?.fee?.balance ?? order.balance_amount;
  const rows: FinancialRow[] = [];

  if (status === "refunded") {
    rows.push({
      key: "deposit",
      label: "定金",
      amount: `¥${depositAmount}`,
      state: "refunded",
      time: fmtTime(application?.refunded_at, formatDateTime),
    });
  } else if (status === "forfeited") {
    rows.push({ key: "deposit", label: "定金", amount: `¥${depositAmount}`, state: "forfeited" });
  } else {
    const depositPaid = ["deposit_paid", "trial_in_progress", "balance_paid", "completed"].includes(status ?? "");
    rows.push({
      key: "deposit",
      label: "定金",
      amount: `¥${depositAmount}`,
      state: depositPaid ? "paid" : "pending",
      time: depositPaid ? fmtTime(application?.deposit_paid_at, formatDateTime) : undefined,
    });
    const balancePaid = ["balance_paid", "completed"].includes(status ?? "");
    rows.push({
      key: "balance",
      label: "尾款",
      amount: `¥${balanceAmount}`,
      state: balancePaid ? "paid" : "pending",
      time: balancePaid ? fmtTime(application?.balance_paid_at, formatDateTime) : undefined,
    });
  }
  return rows;
}

/**
 * B 端口径：从投递列表中挑出"资金状态所属"的那条投递——
 * 优先已进入资金流（定金/试课/尾款/成交）的一条，其次候选，无则 null（显示待收结构）。
 * 纯展示选择，不做业务判断。
 */
export function pickDealApplication(applications: ApplicationItem[]): ApplicationItem | null {
  return (
    applications.find((a) =>
      ["trial_in_progress", "balance_paid", "completed"].includes(a.status)
    ) ||
    applications.find((a) => a.status === "deposit_paid") ||
    applications.find((a) => a.status === "shortlisted") ||
    null
  );
}
