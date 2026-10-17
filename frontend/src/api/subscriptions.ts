import client from "./client";

export interface TeacherSubscription {
  enabled: boolean;
  subjects: string[];
  grades: string[];
  min_base_price: number | null;
  updated_at: string | null;
}

export interface TeacherSubscriptionSave {
  enabled: boolean;
  subjects: string[];
  grades: string[];
  min_base_price: number | null;
}

/** 教员找单订阅：一教员一份偏好，PUT 整体覆盖。
 *  新订单入库后后端按偏好匹配并发站内信（见 Profile 通知）。 */
export const subscriptionsApi = {
  getMine: () =>
    client.get<TeacherSubscription>("/subscriptions/mine").then((r) => r.data),

  saveMine: (data: TeacherSubscriptionSave) =>
    client.put<TeacherSubscription>("/subscriptions/mine", data).then((r) => r.data),
};
