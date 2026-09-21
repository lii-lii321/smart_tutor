/**
 * 金额与时间的统一展示口径。
 * 金额一律保留两位小数并千分位（¥1,234.50）——财务平台不允许 ¥99 与 ¥99.00 混排；
 * 时间统一 YYYY-MM-DD HH:mm。
 *
 * 产品决策（D4，2026-09-12 拍板选 B）：null/空值与 0 统一显示 ¥0.00，
 * 不区分"无数据"与"零"（tests/format.spec.ts 锁定该口径，改动需重新评审）。
 */

export function formatMoney(value: number | string | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "¥0.00";
  }
  return `¥${n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * 后端时间统一存 naive UTC（无时区后缀的 ISO 串）。直接 new Date() 会被浏览器
 * 当成本地时间——东八区用户看到的时间差 8 小时（2026-09-21 用户实测）。
 * 此处统一补 Z 按 UTC 解析；已带时区后缀的串原样交给 Date。
 */
export function parseDbTime(value: string | number | Date): Date {
  if (value instanceof Date || typeof value === "number") {
    return new Date(value);
  }
  let s = value.trim();
  if (/^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$/.test(s)) {
    s = s.replace(" ", "T").replace(/(\.\d{3})\d+$/, "$1") + "Z";
  }
  return new Date(s);
}

export function formatDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const d = parseDbTime(value);
  if (Number.isNaN(d.getTime())) {
    return "-";
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDate(value: string | number | Date | null | undefined): string {
  return formatDateTime(value).slice(0, 10);
}

/**
 * 本地时区的 YYYY-MM-DD。财务/筛选/文件名一律用它，
 * 不要用 toISOString()（UTC）：东八区 0-8 点会把"今天"算成昨天。
 */
export function todayStr(date: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
