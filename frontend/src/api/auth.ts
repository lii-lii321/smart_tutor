import client from "./client";
import type { DetailResponse, MeProfileResponse, TeacherProfile, TokenResponse } from "./types";

export const authApi = {
  me: () =>
    client.get<MeProfileResponse>("/auth/me/profile").then((r) => r.data),

  phoneInviteLogin: (phone: string, inviteCode: string, password: string) =>
    client
      .post<TokenResponse>("/auth/teacher-phone-login", {
        phone,
        invite_code: inviteCode,
        password,
      })
      .then((r) => r.data),

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
    client.post<TokenResponse>("/auth/teacher-phone-register", data).then((r) => r.data),

  ownerLogin: (accessCode: string) =>
    client.post<TokenResponse>("/auth/owner-login", { access_code: accessCode }).then((r) => r.data),

  tenantLogin: (inviteCode: string, password: string) =>
    client
      .post<TokenResponse>("/auth/tenant-login", {
        invite_code: inviteCode,
        password,
      })
      .then((r) => r.data),

  teacherChangePassword: (oldPassword: string, newPassword: string) =>
    client
      .post<DetailResponse>("/auth/teacher-change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      })
      .then((r) => r.data),

  updateTeacherProfile: (data: {
    name?: string;
    gender?: "male" | "female";
    wechat_id?: string;
    school?: string;
    major?: string;
    grade?: string;
    highlights?: string;
    home_area?: string;
    lng?: number;
    lat?: number;
  }) =>
    client.patch<TeacherProfile>("/auth/teacher/profile", data).then((r) => r.data),

  tenantChangePassword: (oldPassword: string, newPassword: string) =>
    client
      .post<DetailResponse>("/auth/tenant-change-password", {
        old_password: oldPassword,
        new_password: newPassword,
      })
      .then((r) => r.data),
};
