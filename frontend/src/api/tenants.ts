import client from "./client";

export interface TenantAdmin {
  id: number;
  tenant_name: string;
  invite_code: string;
  contact_wechat: string;
  is_active: boolean;
  created_at: string;
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

export const tenantsApi = {
  list: () => client.get("/tenants/").then((r) => r.data as TenantAdmin[]),

  demoData: () => client.get("/tenants/demo-data").then((r) => r.data as DemoData),

  seedDemo: () => client.post("/tenants/seed-demo").then((r) => r.data as DemoData),

  create: (data: {
    tenant_name: string;
    contact_wechat: string;
    invite_code?: string;
  }) => client.post("/tenants/", data).then((r) => r.data as TenantAdmin),

  updateStatus: (tenantId: number, isActive: boolean) =>
    client
      .patch(`/tenants/${tenantId}/status`, { is_active: isActive })
      .then((r) => r.data as TenantAdmin),
};
