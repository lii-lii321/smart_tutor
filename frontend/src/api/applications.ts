import client from "./client";
import type {
  ApplicationItem,
  ApplicationSummaryResponse,
  OrderReviewItem,
} from "./types";

export const applicationsApi = {
  apply: (orderId: number, proposedPrice?: number, resumeId?: number) => {
    const body: { order_id: number; proposed_price?: number; resume_id?: number } = {
      order_id: orderId,
    };
    if (proposedPrice != null) body.proposed_price = proposedPrice;
    if (resumeId != null) body.resume_id = resumeId;
    return client.post<ApplicationItem>("/applications/", body).then((r) => r.data);
  },

  // 后端已不支持全量：page_size<=0 按默认页长处理；orderId 传入时只返回该订单的投递
  listMine: (page = 1, pageSize = 20, orderId?: number) =>
    client
      .get<ApplicationItem[]>("/applications/mine", {
        params: { page, page_size: pageSize, ...(orderId != null ? { order_id: orderId } : {}) },
      })
      .then((r) => r.data),

  summary: () =>
    client.get<ApplicationSummaryResponse>("/applications/summary").then((r) => r.data),

  listByOrder: (orderId: number, page = 1, pageSize = 100) =>
    client
      .get<ApplicationItem[]>(`/applications/order/${orderId}`, { params: { page, page_size: pageSize } })
      .then((r) => r.data),

  shortlist: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/shortlist`).then((r) => r.data),

  reject: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/reject`).then((r) => r.data),

  restore: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/restore`).then((r) => r.data),

  startTrial: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/start-trial`).then((r) => r.data),

  confirmDeposit: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/confirm-deposit`).then((r) => r.data),

  confirmBalance: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/confirm-balance`).then((r) => r.data),

  complete: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/complete`).then((r) => r.data),

  trialFailed: (applicationId: number, refundAmount = 0, trialPaidByParent = 0, isTeacherViolated = false) =>
    client
      .post<ApplicationItem>(`/applications/${applicationId}/trial-failed`, {
        refund_amount: refundAmount,
        trial_paid_by_parent: trialPaidByParent,
        is_teacher_violated: isTeacherViolated,
      })
      .then((r) => r.data),

  forfeit: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/forfeit`).then((r) => r.data),

  cancel: (applicationId: number) =>
    client.post<ApplicationItem>(`/applications/${applicationId}/cancel`).then((r) => r.data),

  review: (applicationId: number, rating: number, comment?: string) =>
    client
      .post<OrderReviewItem>(`/applications/${applicationId}/review`, {
        rating,
        comment: comment || null,
      })
      .then((r) => r.data),

  myReviews: (page = 1, pageSize = 50) =>
    client
      .get<OrderReviewItem[]>("/applications/reviews/mine", { params: { page, page_size: pageSize } })
      .then((r) => r.data),

  // 评价精确总数：服务端经 X-Total-Count 响应头返回，不受分页影响（角标等计数场景用）
  myReviewsCount: () =>
    client
      .get<OrderReviewItem[]>("/applications/reviews/mine", { params: { page: 1, page_size: 1 } })
      .then((r) => Number(r.headers["x-total-count"] || 0)),
};
