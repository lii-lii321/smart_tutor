import { describe, expect, it } from "vitest";

import { calcInfoFee, infoFeeRate, MIN_DEPOSIT } from "@/utils/fee";

describe("infoFeeRate", () => {
  it("常规频次费率与后端 calculator.py 一致（接单规则 2026-10-27 版）", () => {
    expect(infoFeeRate(1)).toBe(1.5);
    expect(infoFeeRate(2)).toBe(1.0);
    expect(infoFeeRate(3)).toBe(0.8);
    expect(infoFeeRate(4)).toBe(0.8);
    expect(infoFeeRate(7)).toBe(0.8);
  });

  it("寒暑假不设特殊倍率（新规则未定义，参数仅兼容保留）", () => {
    expect(infoFeeRate(1, true)).toBe(1.5);
    expect(infoFeeRate(3, true)).toBe(0.8);
    expect(infoFeeRate(5, true)).toBe(0.8);
  });
});

describe("calcInfoFee", () => {
  it("信息费 = 周课时费 × 频次倍率，拆分为定金 + 尾款", () => {
    // 200/次 × 2次 × 1.0 = 400
    expect(calcInfoFee(200, 2)).toEqual({ total: 400, deposit: 100, balance: 300, rate: 1.0 });
    // 100/次 × 1次 × 1.5 = 150
    expect(calcInfoFee(100, 1)).toEqual({ total: 150, deposit: 100, balance: 50, rate: 1.5 });
  });

  it("规则文档标准例：一周一次、每次 2h、80/h → 160×1.5 = 240", () => {
    expect(calcInfoFee(160, 1)?.total).toBe(240);
  });

  it("用户校准例：单次 120、每周 5 次 → 600×0.8 = 480", () => {
    expect(calcInfoFee(120, 5)).toEqual({ total: 480, deposit: 100, balance: 380, rate: 0.8 });
  });

  it("课酬无效返回 null", () => {
    expect(calcInfoFee(0, 2)).toBeNull();
    expect(calcInfoFee(-50, 2)).toBeNull();
    expect(calcInfoFee(Number.NaN, 2)).toBeNull();
  });

  it(`信息费低于最低定金 ¥${MIN_DEPOSIT} 返回 null（与后端 ValueError 口径一致）`, () => {
    // 60/次 × 1次 × 1.5 = 90 < 100
    expect(calcInfoFee(60, 1)).toBeNull();
    // 25/次 × 2次 × 1.0 = 50 < 100
    expect(calcInfoFee(25, 2)).toBeNull();
    // 边界：50/次 × 2次 × 1.0 = 100，信息费恰好等于最低定金时通过
    expect(calcInfoFee(50, 2)).toEqual({ total: 100, deposit: 100, balance: 0, rate: 1.0 });
  });
});
