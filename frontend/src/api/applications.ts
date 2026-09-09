import client from "./client";
import type {
  ApplicationItem,
  ApplicationSummaryResponse,
  OrderReviewItem,
} from "./types";

export const applicationsApi = {
  apply: (orderId: number, proposedPrice?: number, resumeId?: number) => {
    const params: Record<string, unknown> = { order_id: orderId };
    if (proposedPrice != null) params.proposed_price = proposedPrice;
    if (resumeId != null) params.resume_id = resumeId;
    return client.post<ApplicationItem>("/applications/", null, { params }).then((r) => r.data);
  },

  listMine: (page = 1, pageSize = 0) =>
    client
      .get<ApplicationItem[]>("/applications/mine", { params: { page, page_size: pageSize || undefined } })
      .then((r) => r.data),

  summary: () =>
    client.get<ApplicationSummaryResponse>("/applications/summary").then((r) => r.data),

  listByOrder: (orderId: number) =>
    client.get<ApplicationItem[]>(`/applications/order/${orderId}`).then((r) => r.data),

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
      .post<ApplicationItem>(`/applications/${applicationId}/trial-failed`, null, {
        params: {
          refund_amount: refundAmount,
          trial_paid_by_parent: trialPaidByParent,
          is_teacher_violated: isTeacherViolated,
        },
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

  myReviews: () =>
    client.get<OrderReviewItem[]>("/applications/reviews/mine").then((r) => r.data),
};
