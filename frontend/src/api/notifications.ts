import client from "./client";

export interface NotificationItem {
  id: number;
  title: string;
  content?: string | null;
  application_id?: number | null;
  order_id?: number | null;
  created_at: string;
  is_read: boolean;
}

export interface NotificationList {
  unread_count: number;
  items: NotificationItem[];
}

export const notificationsApi = {
  mine: () =>
    client.get("/notifications/mine").then((r) => r.data as NotificationList),

  readAll: () =>
    client.post("/notifications/read-all").then((r) => r.data as { marked: number }),
};
