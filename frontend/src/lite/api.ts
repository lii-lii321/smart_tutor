import client from "@/api/client";
import type { PublicOrderBrief } from "@/api/types";

/**
 * 轻薄版橱窗 API：只允许调 /public/* 免鉴权端点（游客态红线——
 * client.ts 的 401 拦截会跳登录页，这里任何需鉴权的调用都不该出现）。
 */

/** GET /public/agent/{code}/board（手写映射 AgentBoardResponse） */
export interface LiteBoardResponse {
  tenant_name: string;
  invite_code: string;
  contact_wechat?: string | null;
  orders: PublicOrderBrief[];
}

/** GET /public/agent/{code}/orders/{id}（后端 PublicOrderDetail 白名单脱敏面） */
export interface LiteOrderDetail {
  id: number;
  grade_subject: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  fuzzy_address: string;
  subway_remark: string | null;
  lng: number;
  lat: number;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  created_at: string;
  raw_text: string;
  requirements: string | null;
  contact_wechat: string | null;
}

export const liteApi = {
  getBoard: (inviteCode: string) =>
    client.get<LiteBoardResponse>(`/public/agent/${inviteCode}/board`).then((r) => r.data),

  getOrderDetail: (inviteCode: string, orderId: number) =>
    client.get<LiteOrderDetail>(`/public/agent/${inviteCode}/orders/${orderId}`).then((r) => r.data),
};
