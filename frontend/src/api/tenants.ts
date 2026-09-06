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

export const tenantsApi = {
  list: () => client.get("/tenants/").then((r) => r.data as TenantAdmin[]),

  stats: () => client.get("/tenants/stats").then((r) => r.data as OwnerStats),

  listTeachers: (params?: { q?: string; banned?: boolean }) =>
    client
      .get("/tenants/teachers", { params })
      .then((r) => r.data as TeacherAdmin[]),

  setTeacherBan: (teacherId: number, isBanned: boolean) =>
    client
      .patch(`/tenants/teachers/${teacherId}/ban`, { is_banned: isBanned })
      .then((r) => r.data as TeacherAdmin),

  demoData: () => client.get("/tenants/demo-data").then((r) => r.data as DemoData),

  seedDemo: () => client.post("/tenants/seed-demo").then((r) => r.data as DemoData),

  create: (data: {
    tenant_name: string;
    contact_wechat: string;
    invite_code?: string;
    password?: string;
  }) => client.post("/tenants/", data).then((r) => r.data as TenantAdmin),

  resetPassword: (tenantId: number) =>
    client
      .post(`/tenants/${tenantId}/reset-password`)
      .then((r) => r.data as TenantAdmin),

  updateStatus: (tenantId: number, isActive: boolean) =>
    client
      .patch(`/tenants/${tenantId}/status`, { is_active: isActive })
      .then((r) => r.data as TenantAdmin),
};
