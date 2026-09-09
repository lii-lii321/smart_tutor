/**
 * 金额与时间的统一展示口径。
 * 金额一律保留两位小数并千分位（¥1,234.50）——财务平台不允许 ¥99 与 ¥99.00 混排；
 * 时间统一 YYYY-MM-DD HH:mm。
 */

export function formatMoney(value: number | string | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "¥0.00";
  }
  return `¥${n.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDateTime(value: string | number | Date | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return "-";
  }
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDate(value: string | number | Date | null | undefined): string {
  return formatDateTime(value).slice(0, 10);
}
