import client from "./client";

export const authApi = {
  me: () => client.get("/auth/me/profile").then((r) => r.data),

  phoneInviteLogin: (phone: string, inviteCode: string, password: string) =>
    client.post("/auth/teacher-phone-login", {
      phone,
      invite_code: inviteCode,
      password,
    }).then((r) => r.data),

  phoneInviteRegister: (data: {
    phone: string;
    invite_code: string;
    password: string;
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

  tenantLogin: (inviteCode: string, password: string) =>
    client.post("/auth/tenant-login", {
      invite_code: inviteCode,
      password,
    }).then((r) => r.data),

  teacherChangePassword: (oldPassword: string, newPassword: string) =>
    client
      .post("/auth/teacher-change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      })
      .then((r) => r.data),

  tenantChangePassword: (oldPassword: string, newPassword: string) =>
    client
      .post("/auth/tenant-change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      })
      .then((r) => r.data),
};
