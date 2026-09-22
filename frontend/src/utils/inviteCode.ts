const AGENT_STORAGE_KEY = "teacher_agent_invite_codes";
/**
 * 无码进入（直接访问根路径）时的兜底橱窗：不拦有意向的陌生访客。
 * 本地 DEV 落演示账号 tx886；生产构建必须用 VITE_DEFAULT_INVITE_CODE 指定
 * 平台自有橱窗（该邀请码须在生产库真实存在，否则无码访客只会看到空地图报错）。
 */
export const DEFAULT_INVITE_CODE =
  (import.meta.env.VITE_DEFAULT_INVITE_CODE || "").trim() || "tx886";

function readTenantInviteCode(): string | null {
  // 教员登录成功后 auth store 会把当前中介写入 localStorage
  try {
    const raw = localStorage.getItem("tenant");
    if (!raw) return null;
    const tenant = JSON.parse(raw);
    const code = tenant?.invite_code;
    return typeof code === "string" && code.trim() ? code.trim() : null;
  } catch {
    return null;
  }
}

function readLastAgentCode(): string | null {
  try {
    const saved = JSON.parse(localStorage.getItem(AGENT_STORAGE_KEY) || "[]");
    if (Array.isArray(saved) && saved[0]) {
      return String(saved[0]);
    }
  } catch {
    // 忽略损坏的本地存储
  }
  return null;
}

/**
 * 教员端跳转橱窗的邀请码解析：路由参数 > 登录中介 > 最近浏览 > 演示默认。
 * 避免各页面硬编码演示邀请码，多租户下不再跳错中介。
 */
export function resolveInviteCode(routeCode?: string | string[]): string {
  if (typeof routeCode === "string" && routeCode.trim()) {
    return routeCode.trim();
  }
  if (Array.isArray(routeCode) && routeCode[0]) {
    return String(routeCode[0]).trim();
  }
  return readTenantInviteCode() || readLastAgentCode() || DEFAULT_INVITE_CODE;
}

export function getLastInviteCode(): string {
  return resolveInviteCode();
}
