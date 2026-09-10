import { describe, expect, it } from "vitest";
import { formatDate, formatDateTime, formatMoney } from "@/utils/format";

describe("formatMoney", () => {
  it("非法输入（null/undefined/非数字串）回退 ¥0.00", () => {
    expect(formatMoney(null)).toBe("¥0.00");
    expect(formatMoney(undefined)).toBe("¥0.00");
    expect(formatMoney("abc")).toBe("¥0.00");
    expect(formatMoney(NaN)).toBe("¥0.00");
    expect(formatMoney(Infinity)).toBe("¥0.00");
  });

  it("保留两位小数并千分位", () => {
    expect(formatMoney(0)).toBe("¥0.00");
    expect(formatMoney(99.5)).toBe("¥99.50");
    expect(formatMoney(1234.5)).toBe("¥1,234.50");
    expect(formatMoney(1234567.891)).toBe("¥1,234,567.89");
    expect(formatMoney("1234.5")).toBe("¥1,234.50");
  });

  it("负数保留符号", () => {
    expect(formatMoney(-1234.5)).toBe("¥-1,234.50");
  });
});

describe("formatDateTime", () => {
  it("空值与非法值返回 -", () => {
    expect(formatDateTime(null)).toBe("-");
    expect(formatDateTime(undefined)).toBe("-");
    expect(formatDateTime("")).toBe("-");
    expect(formatDateTime("not-a-date")).toBe("-");
  });

  it("按本地时间格式化为 YYYY-MM-DD HH:mm", () => {
    expect(formatDateTime(new Date(2026, 0, 2, 3, 4))).toBe("2026-01-02 03:04");
    expect(formatDateTime(new Date(2026, 11, 31, 23, 59))).toBe("2026-12-31 23:59");
  });

  it("接受本地时区 ISO 串与时间戳", () => {
    expect(formatDateTime("2026-01-02T03:04:00")).toBe("2026-01-02 03:04");
    expect(formatDateTime(new Date(2026, 5, 1, 8, 5).getTime())).toBe("2026-06-01 08:05");
  });
});

describe("formatDate", () => {
  it("截取日期部分", () => {
    expect(formatDate(new Date(2026, 0, 2, 23, 59))).toBe("2026-01-02");
    expect(formatDate(null)).toBe("-");
  });
});
