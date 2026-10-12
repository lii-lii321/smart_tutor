import client from "./client";

export interface FindOrderConditions {
  subject?: string | null;
  grade?: string | null;
  min_base_price?: number | null;
  max_base_price?: number | null;
  radius_km?: number | null;
  anchor?: string | null;
}

/** 找单结果卡片：订单列表同款字段 + 距离（无距离条件时为 null） */
export interface AiOrderItem {
  id: number;
  raw_id: string;
  grade_subject: string;
  price_total: string;
  base_price: number;
  fuzzy_address: string;
  status: string;
  needs_manual_price: boolean;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  weekly_frequency: number;
  lng: number;
  lat: number;
  created_at: string | null;
  expired_at: string | null;
  distance_km: number | null;
}

export interface FindOrdersResponse {
  conditions: FindOrderConditions;
  warnings: string[];
  total_matched: number;
  scanned: number;
  items: AiOrderItem[];
}

/**
 * AI 助手：自然语言找单（阶段 1a）。
 * AI 只负责把人话解析成筛选条件；查询与结果与订单管理页同一数据口径，
 * 条件 chips + warnings 原样展示，结果永远可在订单管理页人工复核。
 */
export const aiApi = {
  findOrders: (query: string) =>
    client.post<FindOrdersResponse>("/ai/find-orders", { query }).then((r) => r.data),
};
