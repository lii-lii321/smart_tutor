import { describe, expect, it } from "vitest";

import { calcInfoFee, infoFeeRate, MIN_DEPOSIT } from "@/utils/fee";

describe("infoFeeRate", () => {
  it("常规频次费率与后端 calculator.py 一致", () => {
    expect(infoFeeRate(1)).toBe(1.5);
    expect(infoFeeRate(2)).toBe(1.0);
    expect(infoFeeRate(3)).toBe(0.9);
    expect(infoFeeRate(4)).toBe(0.8);
    expect(infoFeeRate(7)).toBe(0.8);
  });

  it("寒暑假单一律 2.5 倍（频次不参与）", () => {
    expect(infoFeeRate(1, true)).toBe(2.5);
    expect(infoFeeRate(3, true)).toBe(2.5);
    expect(infoFeeRate(5, true)).toBe(2.5);
  });
});

describe("calcInfoFee", () => {
  it("拆分为定金 + 尾款", () => {
    expect(calcInfoFee(200, 2)).toEqual({ total: 200, deposit: 100, balance: 100, rate: 1.0 });
    expect(calcInfoFee(100, 1)).toEqual({ total: 150, deposit: 100, balance: 50, rate: 1.5 });
  });

  it("寒暑假单按 2.5 倍计算（此前的前端副本漏掉该分支）", () => {
    expect(calcInfoFee(100, 2, true)?.total).toBe(250);
    expect(calcInfoFee(100, 3, true)?.rate).toBe(2.5);
  });

  it("课酬无效返回 null", () => {
    expect(calcInfoFee(0, 2)).toBeNull();
    expect(calcInfoFee(-50, 2)).toBeNull();
    expect(calcInfoFee(Number.NaN, 2)).toBeNull();
  });

  it(`信息费低于最低定金 ¥${MIN_DEPOSIT} 返回 null（与后端 ValueError 口径一致）`, () => {
    // 60 × 1.5 = 90 < 100
    expect(calcInfoFee(60, 1)).toBeNull();
    // 100 × 0.8 = 80 < 100，同样拒绝
    expect(calcInfoFee(100, 4)).toBeNull();
    // 边界：125 × 0.8 = 100，信息费恰好等于最低定金时通过
    expect(calcInfoFee(125, 4)).toEqual({ total: 100, deposit: 100, balance: 0, rate: 0.8 });
  });
});
