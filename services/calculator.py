"""
精算模块：信息费计算 + 试课退费精算。

金额一律用 Decimal（ROUND_HALF_UP，四舍五入到分）计算，
避免二进制浮点的银行家舍入误差（如 round(2.675, 2) == 2.67）累积到对账；
边界层（schema/JSON）负责与 float 互转。
"""
from decimal import ROUND_HALF_UP, Decimal

# 锁定定金（平台规则，调整费率时改这里）
DEPOSIT = Decimal("100.00")

_TWO_PLACES = Decimal("0.01")


def _money(value) -> Decimal:
    """任意数值 → 两位小数 Decimal，半进一舍入。"""
    return Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# 每周频次 → 信息费倍率
_WEEKLY_RATES: dict[str, Decimal] = {
    "summer": Decimal("2.5"),
    "once": Decimal("1.5"),
    "twice": Decimal("1.0"),
    "thrice": Decimal("0.9"),
    "more": Decimal("0.8"),
}


def _rate_for(weekly_frequency: int, is_summer_vacation: bool) -> Decimal:
    if is_summer_vacation:
        return _WEEKLY_RATES["summer"]
    if weekly_frequency == 1:
        return _WEEKLY_RATES["once"]
    if weekly_frequency == 2:
        return _WEEKLY_RATES["twice"]
    if weekly_frequency == 3:
        return _WEEKLY_RATES["thrice"]
    return _WEEKLY_RATES["more"]


def calculate_info_fee(base_price, weekly_frequency: int, is_summer_vacation: bool) -> dict:
    """
    根据行业标准计算全额信息费、定金与尾款。

    费率规则：
        - 寒暑假单：2.5 倍单次课酬
        - 一周 1 次：1.5 倍
        - 一周 2 次：1.0 倍
        - 一周 3 次：0.9 倍
        - 一周 4 次及以上：0.8 倍
    """
    base = _money(base_price)
    if base <= 0:
        raise ValueError(f"课酬金额({base_price})无效，请检查文本中的薪资信息是否正确")

    total_info_fee = _money(base * _rate_for(weekly_frequency, is_summer_vacation))

    if total_info_fee < DEPOSIT:
        raise ValueError(f"信息费 ¥{total_info_fee} 低于最低定金 ¥{DEPOSIT}，课酬({base_price})可能过低")

    return {
        "total_info_fee": total_info_fee,
        "deposit": DEPOSIT,
        "balance": _money(total_info_fee - DEPOSIT),
    }


def calculate_refund(
    total_info_fee_paid,
    trial_paid_by_parent,
    is_trial_success: bool,
    is_teacher_violated: bool,
) -> Decimal:
    """
    试课失败退费精算公式：

        退费金额 = max(0, 已交信息费 − 家长支付的试课薪酬 × 70%)

    若试课成功或教员违规，退费金额为 0。
    """
    if is_teacher_violated or is_trial_success:
        return Decimal("0.00")

    refund_amount = _money(total_info_fee_paid) - _money(_money(trial_paid_by_parent) * Decimal("0.7"))
    return max(Decimal("0.00"), refund_amount)
