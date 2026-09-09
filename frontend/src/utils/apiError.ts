import axios from "axios";

/**
 * 从任意抛出的错误中提取适合 toast 展示的文案。
 * - FastAPI 422 的 detail 是 [{loc, msg}] 数组，拼接成可读文本；
 * - 字符串 detail 直接透出（后端业务提示）；
 * - 断网/超时（无 response）给网络提示；
 * - 其余回退到调用方给的兜底文案。
 */
export function getApiErrorMessage(e: unknown, fallback = "操作失败，请稍后重试"): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((item: { msg?: string; loc?: unknown[] }) => {
          const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
          return field && item.msg ? `${field}: ${item.msg}` : item.msg || "输入有误";
        })
        .join("；");
    }
    if (!e.response) {
      return "网络异常，请检查网络后重试";
    }
  }
  if (e instanceof Error && e.message && !e.message.includes("Request failed")) {
    return e.message;
  }
  return fallback;
}

/** 提取 HTTP 状态码；非 axios 错误（网络断开/脚本异常）返回 null。 */
export function getApiErrorStatus(e: unknown): number | null {
  if (axios.isAxiosError(e)) {
    return e.response?.status ?? null;
  }
  return null;
}
