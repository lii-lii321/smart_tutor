import client from "./client";

export interface TenantAdmin {
  id: number;
  tenant_name: string;
  invite_code: string;
  contact_wechat: string;
  is_active: boolean;
  created_at: string;
  /** 仅创建/重置密码时返回一次明文，其余场景为 null */
  initial_password?: string | null;
}

export interface DemoTeacher {
  id: number;
  name: string;
  phone: string;
  school: string;
  major?: string | null;
  grade?: string | null;
  highlights?: string | null;
  teaching_subjects?: string | null;
  teaching_grades?: string | null;
}

export interface DemoData {
  counts: {
    tenants: number;
    teachers: number;
    resumes: number;
  };
  tenants: TenantAdmin[];
  teachers: DemoTeacher[];
}

export interface TeacherAdmin {
  id: number;
  name: string;
  gender: "male" | "female";
  phone: string;
  school: string;
  major?: string | null;
  grade?: string | null;
  is_banned: boolean;
  created_at: string;
}

export interface OwnerStats {
  tenant_count: number;
  active_tenant_count: number;
  teacher_count: number;
  banned_teacher_count: number;
  orders_recruiting: number;
  orders_trial: number;
  orders_completed: number;
  orders_archived: number;
  gmv_total: number;
  refund_total: number;
  forfeit_total: number;
  funnel: {
    applications_total: number;
    shortlisted: number;
    deposit_paid: number;
    completed: number;
  };
  ranking: {
    tenant_id: number;
    tenant_name: string;
    invite_code: string;
    is_active: boolean;
    orders_total: number;
    orders_recruiting: number;
    orders_completed: number;
    applications_total: number;
    gmv: number;
  }[];
}

export interface MyTeacher {
  teacher_id: number;
  name: string;
  phone: string;
  school?: string | null;
  gender: "male" | "female";
  applications_total: number;
  completed_count: number;
  violation_count: number;
  avg_rating?: number | null;
  is_blacklisted: boolean;
  last_applied_at?: string | null;
}

export interface TenantRoiSummary {
  /** UTC 自然月，格式 YYYY-MM */
  month: string;
  orders_imported: number;
  applications_received: number;
  deals_completed: number;
  deposit_in: number;
  balance_in: number;
  refund_out: number;
  forfeit: number;
  net_amount: number;
  teacher_pool: number;
}

/** 拉黑返回项（后端 BlacklistItem） */
export interface BlacklistItem {
  teacher_id: number;
  name: string;
  phone?: string | null;
  reason?: string | null;
  created_at: string;
}

export interface BlacklistStatusItem {
  tenant_id: number;
  tenant_name: string;
  reason?: string | null;
  created_at: string;
}

export const tenantsApi = {
  list: () => client.get<TenantAdmin[]>("/tenants/").then((r) => r.data),

  stats: () => client.get<OwnerStats>("/tenants/stats").then((r) => r.data),

  roiSummary: () =>
    client.get<TenantRoiSummary>("/tenants/me/roi-summary").then((r) => r.data),

  myTeachers: () =>
    client.get<MyTeacher[]>("/tenants/my-teachers").then((r) => r.data),

  blacklist: (teacherId: number, reason?: string) =>
    client
      .post<BlacklistItem>(`/tenants/teachers/${teacherId}/blacklist`, { reason: reason || null })
      .then((r) => r.data),

  unblacklist: (teacherId: number) =>
    client
      .delete<{ ok: boolean }>(`/tenants/teachers/${teacherId}/blacklist`)
      .then((r) => r.data),

  myTeachersExportUrl: () => "/tenants/my-teachers/export",

  myBlacklistStatus: () =>
    client.get<BlacklistStatusItem[]>("/tenants/blacklist-status").then((r) => r.data),

  listTeachers: (params?: {
    q?: string;
    banned?: boolean;
    page?: number;
    page_size?: number;
  }) =>
    client.get<TeacherAdmin[]>("/tenants/teachers", { params }).then((r) => r.data),

  setTeacherBan: (teacherId: number, isBanned: boolean) =>
    client
      .patch<TeacherAdmin>(`/tenants/teachers/${teacherId}/ban`, { is_banned: isBanned })
      .then((r) => r.data),

  demoData: () => client.get<DemoData>("/tenants/demo-data").then((r) => r.data),

  seedDemo: () => client.post<DemoData>("/tenants/seed-demo").then((r) => r.data),

  create: (data: {
    tenant_name: string;
    contact_wechat: string;
    invite_code?: string;
    password?: string;
  }) => client.post<TenantAdmin>("/tenants/", data).then((r) => r.data),

  resetPassword: (tenantId: number) =>
    client
      .post<TenantAdmin>(`/tenants/${tenantId}/reset-password`)
      .then((r) => r.data),

  updateStatus: (tenantId: number, isActive: boolean) =>
    client
      .patch<TenantAdmin>(`/tenants/${tenantId}/status`, { is_active: isActive })
      .then((r) => r.data),
};
