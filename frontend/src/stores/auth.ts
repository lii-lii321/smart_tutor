import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { authApi } from "@/api/auth";
import type { MeProfileResponse, TeacherProfile, TenantBriefInfo } from "@/api/types";

// 类型统一走 api/types（与后端 TeacherResponse/TenantBrief 对齐），旧名保留导出兼容既有引用
export type TeacherInfo = TeacherProfile;
export type TenantBrief = TenantBriefInfo;

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(localStorage.getItem("token") || "");
  const role = ref<string>(localStorage.getItem("role") || "");
  const teacher = ref<TeacherInfo | null>(readStoredJson<TeacherInfo>("teacher"));
  const tenant = ref<TenantBrief | null>(readStoredJson<TenantBrief>("tenant"));

  const isLoggedIn = computed(() => !!token.value);
  const isTeacher = computed(() => role.value === "teacher");
  const isAdmin = computed(() => role.value === "tenant_admin" || role.value === "super_admin");

  function setAuth(t: string, r: string, tInfo?: TeacherProfile | null, ten?: TenantBriefInfo | null) {
    token.value = t;
    role.value = r;
    teacher.value = tInfo || null;
    tenant.value = ten || null;
    resetMeCache();
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
    resetMeCache();
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("teacher");
    localStorage.removeItem("tenant");
  }

  function setTeacher(t: TeacherProfile) {
    teacher.value = t;
    writeStoredJson("teacher", teacher.value);
  }

  // 路由守卫每次导航都会调 fetchMe：TTL 缓存 + in-flight 去重，
  // 避免移动端弱网下每次切页都同步等一次 /me/profile。改密/登出等强校验场景传 force。
  const ME_CACHE_TTL = 60_000;
  let meInFlight: Promise<MeProfileResponse | null> | null = null;
  let meFetchedAt = 0;
  let meLastResult: MeProfileResponse | null = null;

  function resetMeCache() {
    meInFlight = null;
    meFetchedAt = 0;
    meLastResult = null;
  }

  async function fetchMe(force = false) {
    if (!token.value) {
      return null;
    }
    if (!force && meInFlight) {
      return meInFlight;
    }
    if (!force && meLastResult && Date.now() - meFetchedAt < ME_CACHE_TTL) {
      return meLastResult;
    }

    meInFlight = (async () => {
      const res = await authApi.me();
      role.value = res.role || role.value;
      teacher.value = res.teacher || null;
      tenant.value = res.tenant || null;
      localStorage.setItem("role", role.value);
      writeStoredJson("teacher", teacher.value);
      writeStoredJson("tenant", tenant.value);
      meLastResult = res;
      meFetchedAt = Date.now();
      return res;
    })();

    try {
      return await meInFlight;
    } catch (e) {
      // 失败不缓存，下次导航重新校验
      resetMeCache();
      throw e;
    } finally {
      meInFlight = null;
    }
  }

  async function phoneInviteLogin(phone: string, inviteCode: string, password: string) {
    const res = await authApi.phoneInviteLogin(phone, inviteCode, password);
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

  async function tenantLogin(inviteCode: string, password: string) {
    const res = await authApi.tenantLogin(inviteCode, password);
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
    setTeacher,
    logout,
    phoneInviteLogin,
    phoneInviteRegister,
    ownerLogin,
    tenantLogin,
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
