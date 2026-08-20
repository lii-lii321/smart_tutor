import client from "./client";

export const authApi = {
  me: () => client.get("/auth/me/profile").then((r) => r.data),

  devLogin: (openid: string) =>
    client.post("/auth/dev-login", null, { params: { openid } }).then((r) => r.data),

  devRegister: (openid: string, name: string) =>
    client.post("/auth/dev-register", null, { params: { openid, name } }).then((r) => r.data),

  phoneInviteLogin: (phone: string, inviteCode: string) =>
    client.post("/auth/teacher-phone-login", {
      phone,
      invite_code: inviteCode,
    }).then((r) => r.data),

  phoneInviteRegister: (data: {
    phone: string;
    invite_code: string;
    name: string;
    gender: "male" | "female";
    wechat_id: string;
    school: string;
    is_985_211: boolean;
    is_985: boolean;
    is_211: boolean;
    is_double_first_class: boolean;
    major?: string;
    grade?: string;
    highlights?: string;
  }) =>
    client.post("/auth/teacher-phone-register", data).then((r) => r.data),

  ownerLogin: (accessCode: string) =>
    client.post("/auth/owner-login", { access_code: accessCode }).then((r) => r.data),

  tenantLogin: (inviteCode: string) =>
    client.post("/auth/tenant-login", { invite_code: inviteCode }).then((r) => r.data),

  devTenant: (inviteCode: string, tenantName?: string) =>
    client.post("/auth/dev-tenant", null, {
      params: { invite_code: inviteCode, tenant_name: tenantName },
    }).then((r) => r.data),
};
