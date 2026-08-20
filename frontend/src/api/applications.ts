import client from "./client";

export const applicationsApi = {
  apply: (orderId: number, proposedPrice?: number, resumeId?: number) => {
    const params: Record<string, any> = { order_id: orderId };
    if (proposedPrice != null) params.proposed_price = proposedPrice;
    if (resumeId != null) params.resume_id = resumeId;
    return client.post("/applications/", null, { params }).then((r) => r.data);
  },

  listMine: () =>
    client.get("/applications/mine").then((r) => r.data),

  listByOrder: (orderId: number) =>
    client.get(`/applications/order/${orderId}`).then((r) => r.data),

  shortlist: (applicationId: number) =>
    client.post(`/applications/${applicationId}/shortlist`).then((r) => r.data),

  startTrial: (applicationId: number) =>
    client.post(`/applications/${applicationId}/start-trial`).then((r) => r.data),

  confirmDeposit: (applicationId: number) =>
    client.post(`/applications/${applicationId}/confirm-deposit`).then((r) => r.data),

  confirmBalance: (applicationId: number) =>
    client.post(`/applications/${applicationId}/confirm-balance`).then((r) => r.data),

  complete: (applicationId: number) =>
    client.post(`/applications/${applicationId}/complete`).then((r) => r.data),

  trialFailed: (applicationId: number, refundAmount = 0, trialPaidByParent = 0, isTeacherViolated = false) =>
    client
      .post(`/applications/${applicationId}/trial-failed`, null, {
        params: {
          refund_amount: refundAmount,
          trial_paid_by_parent: trialPaidByParent,
          is_teacher_violated: isTeacherViolated,
        },
      })
      .then((r) => r.data),

  forfeit: (applicationId: number) =>
    client.post(`/applications/${applicationId}/forfeit`).then((r) => r.data),

  cancel: (applicationId: number) =>
    client.post(`/applications/${applicationId}/cancel`).then((r) => r.data),
};
