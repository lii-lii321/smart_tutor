import client from "./client";

export const ordersApi = {
  batchParse: (rawText: string) =>
    client.post("/orders/batch-parse", { raw_text: rawText }).then((r) => r.data),

  batchImport: (items: any[]) =>
    client.post("/orders/batch-import", { items }).then((r) => r.data),

  listOrders: (page = 1, pageSize = 20, status?: string) =>
    client.get("/orders/", { params: { page, page_size: pageSize, status } }).then((r) => r.data),

  getOrder: (orderId: number) =>
    client.get(`/orders/${orderId}`).then((r) => r.data),

  transitStatus: (orderId: number, targetStatus: string) =>
    client.post(`/orders/${orderId}/transit`, { target_status: targetStatus }).then((r) => r.data),

  updateOrder: (orderId: number, data: Record<string, any>) =>
    client.patch(`/orders/${orderId}`, data).then((r) => r.data),

  archive: (orderId: number) =>
    client.post(`/orders/${orderId}/archive`).then((r) => r.data),

  republish: (orderId: number) =>
    client.post(`/orders/${orderId}/republish`).then((r) => r.data),

  expireStale: () =>
    client.post("/orders/expire-stale").then((r) => r.data),

  addressUnlock: (orderId: number) =>
    client.get(`/orders/${orderId}/address-unlock`).then((r) => r.data),
};

export const publicApi = {
  getBoard: (inviteCode: string) =>
    client.get(`/public/agent/${inviteCode}/board`).then((r) => r.data),
};
