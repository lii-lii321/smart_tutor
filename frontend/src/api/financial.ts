import client from "./client";
import type {
  FinancialSummaryResponse,
  FinancialType,
  TeacherFeeSummaryResponse,
} from "./types";

export type FinancialTypeFilter = FinancialType;

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
      .get<FinancialSummaryResponse>("/financial-records/", {
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

  // 教员结算单：我的费用（流水分页返回，汇总不受分页影响）
  myFees: (page = 1, pageSize = 50) =>
    client
      .get<TeacherFeeSummaryResponse>("/financial-records/mine", { params: { page, page_size: pageSize } })
      .then((r) => r.data),

  myFeesExportUrl: () => "/financial-records/mine/export",

  /** 上传收款凭证（转账截图）：返回更新后的流水（含 has_receipt） */
  uploadReceipt: (recordId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return client
      .post(`/financial-records/${recordId}/receipt`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  /** 凭证图片地址：图片本体必须经鉴权端点读取（axios 附 token 后取 blob） */
  receiptUrl: (recordId: number) => `/financial-records/${recordId}/receipt`,
};
