import client from "./client";
import type {
  AddressUnlockResponse,
  BatchImportResponse,
  BatchStatusUpdateResponse,
  OrderDetail,
  OrderListResponse,
  TransitResponse,
} from "./types";

export const ordersApi = {
  batchParse: (rawText: string) =>
    client.post("/orders/batch-parse", { raw_text: rawText }).then((r) => r.data),

  batchImport: (items: unknown[]) =>
    client.post("/orders/batch-import", { items }).then((r) => r.data as BatchImportResponse),

  listOrders: (page = 1, pageSize = 20, status?: string, q?: string) =>
    client
      .get<OrderListResponse>("/orders/", { params: { page, page_size: pageSize, status, q } })
      .then((r) => r.data),

  getOrder: (orderId: number) =>
    client.get<OrderDetail>(`/orders/${orderId}`).then((r) => r.data),

  batchStatus: (orderIds: number[], targetStatus: string) =>
    client
      .post<BatchStatusUpdateResponse>("/orders/batch-status", { order_ids: orderIds, target_status: targetStatus })
      .then((r) => r.data),

  updateOrder: (orderId: number, data: Record<string, unknown>) =>
    client.patch<OrderDetail>(`/orders/${orderId}`, data).then((r) => r.data),

  archive: (orderId: number) =>
    client.post<OrderDetail>(`/orders/${orderId}/archive`).then((r) => r.data),

  republish: (orderId: number) =>
    client.post<OrderDetail>(`/orders/${orderId}/republish`).then((r) => r.data),

  addressUnlock: (orderId: number) =>
    client.get<AddressUnlockResponse>(`/orders/${orderId}/address-unlock`).then((r) => r.data),

  ordersExportUrl: (status?: string, q?: string) => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (q) params.append("q", q);
    const qs = params.toString();
    return `/orders/export${qs ? `?${qs}` : ""}`;
  },
};

export const publicApi = {
  getBoard: (inviteCode: string) =>
    client.get(`/public/agent/${inviteCode}/board`).then((r) => r.data),

  getRecommendations: (inviteCode: string, limit = 12) =>
    client.get(`/recommendations/${inviteCode}`, { params: { limit } }).then((r) => r.data),
};
