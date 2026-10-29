/**
 * 信息费预览计算——与后端 services/calculator.py 费率单一对齐。
 *
 * 计费规则（2026-10-27《接单规则》校准，后端为权威源，调整时两侧同步）：
 *   - 信息费 = 周课时费 × 频次倍率；周课时费 = 单次课酬 × 每周次数
 *   - 频次倍率：一周 1 次 ×1.5 / 2 次 ×1.0 / ≥3 次 ×0.8（寒暑假不设特殊倍率）
 *   - 定金锁定 ¥100，信息费不足最低定金视为课酬过低
 *
 * 后端金额用 Decimal HALF_UP 精算；此处的预览仅用于展示，
 * 用"分"整数四舍五入（Math.round），浮点边缘可能与后端差 1 分，以接口下发为准。
 */

export const MIN_DEPOSIT = 100;

export function infoFeeRate(weeklyFrequency: number): number {
  if (weeklyFrequency <= 1) return 1.5;
  if (weeklyFrequency === 2) return 1.0;
  return 0.8;
}

export interface FeePreview {
  total: number;
  deposit: number;
  balance: number;
  rate: number;
}

/** 全额信息费预览；课酬无效或信息费低于最低定金时返回 null（与后端 ValueError 口径一致）。
 *  isSummerVacation 参数仅为调用方兼容保留，新规则不设寒暑假特殊倍率。 */
export function calcInfoFee(
  basePrice: number,
  weeklyFrequency: number,
  _isSummerVacation = false,
): FeePreview | null {
  const base = Math.round(basePrice * 100) / 100;
  if (!base || base <= 0) return null;
  const weekly = Math.max(1, Math.floor(weeklyFrequency) || 1);
  const rate = infoFeeRate(weekly);
  const weeklyTotal = Math.round(base * weekly * 100) / 100;
  const total = Math.round(weeklyTotal * rate * 100) / 100;
  if (total < MIN_DEPOSIT) return null;
  return {
    total,
    deposit: MIN_DEPOSIT,
    balance: Math.round((total - MIN_DEPOSIT) * 100) / 100,
    rate,
  };
}
