import client from "./client";
import type { MarkedResponse, NotificationList, UnreadCountResponse } from "./types";

export type { NotificationItem, NotificationList } from "./types";

export const notificationsApi = {
  mine: () =>
    client.get<NotificationList>("/notifications/mine").then((r) => r.data),

  // 角标轮询专用轻量端点：只回未读数，不拉列表
  unreadCount: () =>
    client.get<UnreadCountResponse>("/notifications/mine/unread-count").then((r) => r.data.unread_count),

  readAll: () =>
    client.post<MarkedResponse>("/notifications/read-all").then((r) => r.data),

  // 批量删除（软删：调度器去重依赖通知行存在，只清内容不改行数）
  deleteMine: (ids: number[]) =>
    client.post<MarkedResponse>("/notifications/delete", { ids }).then((r) => r.data),

  deleteAllMine: () =>
    client.post<MarkedResponse>("/notifications/delete-all").then((r) => r.data),

  deleteTenant: (ids: number[]) =>
    client.post<MarkedResponse>("/notifications/tenant-delete", { ids }).then((r) => r.data),

  deleteAllTenant: () =>
    client.post<MarkedResponse>("/notifications/tenant-delete-all").then((r) => r.data),

  tenantMine: () =>
    client.get<NotificationList>("/notifications/tenant-mine").then((r) => r.data),

  tenantUnreadCount: () =>
    client.get<UnreadCountResponse>("/notifications/tenant-unread-count").then((r) => r.data.unread_count),

  tenantReadAll: () =>
    client.post<MarkedResponse>("/notifications/tenant-read-all").then((r) => r.data),
};
