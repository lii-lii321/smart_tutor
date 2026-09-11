import client from "./client";
import type { MarkedResponse, NotificationList } from "./types";

export type { NotificationItem, NotificationList } from "./types";

export const notificationsApi = {
  mine: () =>
    client.get<NotificationList>("/notifications/mine").then((r) => r.data),

  readAll: () =>
    client.post<MarkedResponse>("/notifications/read-all").then((r) => r.data),

  tenantMine: () =>
    client.get<NotificationList>("/notifications/tenant-mine").then((r) => r.data),

  tenantReadAll: () =>
    client.post<MarkedResponse>("/notifications/tenant-read-all").then((r) => r.data),
};
