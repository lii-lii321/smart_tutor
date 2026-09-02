import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "@/api/auth";

export interface TeacherInfo {
  id: number;
  name: string;
  gender: string;
  school: string;
  is_985_211: boolean;
  is_985: boolean;
  is_211: boolean;
  is_double_first_class: boolean;
  major?: string;
  grade?: string;
  highlights?: string;
  lng?: number | null;
  lat?: number | null;
}

export interface TenantBrief {
  id: number;
  tenant_name: string;
  invite_code: string;
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(localStorage.getItem("token") || "");
  const role = ref<string>(localStorage.getItem("role") || "");
  const teacher = ref<TeacherInfo | null>(readStoredJson<TeacherInfo>("teacher"));
  const tenant = ref<TenantBrief | null>(readStoredJson<TenantBrief>("tenant"));

  const isLoggedIn = computed(() => !!token.value);
  const isTeacher = computed(() => role.value === "teacher");
  const isAdmin = computed(() => role.value === "tenant_admin" || role.value === "super_admin");

  function setAuth(t: string, r: string, tInfo?: TeacherInfo | null, ten?: TenantBrief | null) {
    token.value = t;
    role.value = r;
    teacher.value = tInfo || null;
    tenant.value = ten || null;
    localStorage.setItem("token", t);
    localStorage.setItem("role", r);
    writeStoredJson("teacher", teacher.value);
    writeStoredJson("tenant", tenant.value);
  }

  function logout() {
    token.value = "";
    role.value = "";
    teacher.value = null;
    tenant.value = null;
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("teacher");
    localStorage.removeItem("tenant");
  }

  async function fetchMe() {
    if (!token.value) {
      return null;
    }
    const res = await authApi.me();
    role.value = res.role || role.value;
    teacher.value = res.teacher || null;
    tenant.value = res.tenant || null;
    localStorage.setItem("role", role.value);
    writeStoredJson("teacher", teacher.value);
    writeStoredJson("tenant", tenant.value);
    return res;
  }

  async function devLogin(openid: string) {
    const res = await authApi.devLogin(openid);
    setAuth(res.token, res.role, res.teacher, res.tenant);
    return res;
  }

  async function devRegister(openid: string, name: string) {
    const res = await authApi.devRegister(openid, name);
    setAuth(res.token, res.role, res.teacher, res.tenant);
    return res;
  }

  async function phoneInviteLogin(phone: string, inviteCode: string) {
    const res = await authApi.phoneInviteLogin(phone, inviteCode);
    setAuth(res.token, res.role, res.teacher, res.tenant);
    return res;
  }

  async function phoneInviteRegister(data: Parameters<typeof authApi.phoneInviteRegister>[0]) {
    const res = await authApi.phoneInviteRegister(data);
    setAuth(res.token, res.role, res.teacher, res.tenant);
    return res;
  }

  async function ownerLogin(accessCode: string) {
    const res = await authApi.ownerLogin(accessCode);
    setAuth(res.token, res.role, undefined, undefined);
    return res;
  }

  async function tenantLogin(inviteCode: string) {
    const res = await authApi.tenantLogin(inviteCode);
    setAuth(res.token, res.role, undefined, res.tenant);
    return res;
  }

  async function devTenant(inviteCode: string, tenantName?: string) {
    const res = await authApi.devTenant(inviteCode, tenantName);
    setAuth(res.token, res.role, undefined, res.tenant);
    return res;
  }

  return {
    token,
    role,
    teacher,
    tenant,
    isLoggedIn,
    isTeacher,
    isAdmin,
    setAuth,
    logout,
    devLogin,
    devRegister,
    phoneInviteLogin,
    phoneInviteRegister,
    ownerLogin,
    tenantLogin,
    devTenant,
    fetchMe,
  };
});

function readStoredJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function writeStoredJson(key: string, value: unknown) {
  if (value) {
    localStorage.setItem(key, JSON.stringify(value));
    return;
  }
  localStorage.removeItem(key);
}
