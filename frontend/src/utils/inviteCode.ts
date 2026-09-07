const AGENT_STORAGE_KEY = "teacher_agent_invite_codes";
const DEFAULT_INVITE_CODE = "tx886";

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
