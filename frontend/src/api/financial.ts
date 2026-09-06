import client from "./client";

export type FinancialTypeFilter = "deposit_in" | "balance_in" | "refund_out" | "forfeit";

export interface FinancialFilters {
  type?: FinancialTypeFilter;
  start_date?: string;
  end_date?: string;
}

function toParams(filters?: FinancialFilters) {
  return {
    type: filters?.type,
    start_date: filters?.start_date,
    end_date: filters?.end_date,
  };
}

export const financialApi = {
  list: (page = 1, pageSize = 50, filters?: FinancialFilters) =>
    client
      .get("/financial-records/", {
        params: { page, page_size: pageSize, ...toParams(filters) },
      })
      .then((r) => r.data),

  exportUrl: (filters?: FinancialFilters) => {
    const params = new URLSearchParams();
    const cleaned = toParams(filters);
    Object.entries(cleaned).forEach(([key, value]) => {
      if (value) params.append(key, String(value));
    });
    const qs = params.toString();
    return `/financial-records/export${qs ? `?${qs}` : ""}`;
  },

  // 教员结算单：我的费用
  myFees: () =>
    client.get("/financial-records/mine").then(
      (r) =>
        r.data as {
          total_paid: number;
          total_refunded: number;
          total_forfeit: number;
          records: {
            id: number;
            order_id: number;
            amount: number;
            type: string;
            remark?: string | null;
            created_at: string;
          }[];
        },
    ),
};
