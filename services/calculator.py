"""
精算模块：信息费计算 + 试课退费精算。

金额一律用 Decimal（ROUND_HALF_UP，四舍五入到分），避免二进制浮点的
银行家舍入误差（如 round(2.675, 2) == 2.67）累积到对账；边界层（schema/JSON）
负责与 float 互转。

计费规则（2026-10-27 用户校准《接单规则》，替代旧"单次课酬 × 倍率"口径）：

    信息费 = 周课时费 × 频次倍率
    周课时费 = 单次课酬 × 每周次数
    频次倍率：一周 1 次 ×1.5；一周 2 次 ×1.0；一周 3 次及以上 ×0.8
    定金固定 100 元（死数），尾款 = 信息费 − 定金

    校验例：一周一次、每次 2h、80/h 的单子 → 80×2×1.5 = 240 元。
    线上单（恒 1.5 倍）、指定次数/月薪单（总工资 20%）、机构单（固定信息费）
    在现行数据模型无标记字段，录单走「自带价待定价」路径人工精算，不经本函数。
    is_summer_vacation 参数仅为兼容既有调用与存储保留，新规则不设寒暑假倍率。
"""
from decimal import ROUND_HALF_UP, Decimal

# 锁定定金（平台规则，调整费率时改这里）
DEPOSIT = Decimal("100.00")

_TWO_PLACES = Decimal("0.01")


def _money(value) -> Decimal:
    """任意数值 → 两位小数 Decimal，半进一舍入。"""
    return Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _rate_for(weekly_frequency: int) -> Decimal:
    if weekly_frequency <= 1:
        return Decimal("1.5")
    if weekly_frequency == 2:
        return Decimal("1.0")
    return Decimal("0.8")


def calculate_info_fee(base_price, weekly_frequency: int, is_summer_vacation: bool = False) -> dict:
    """
    根据接单规则计算全额信息费、定金与尾款：信息费 = 周课时费 × 频次倍率。
    is_summer_vacation 兼容保留、不参与计算（新规则无寒暑假特殊倍率）。
    信息费不足最低定金说明课酬过低，由导入/投递路径拦截（拒绝或转待定价）。
    """
    base = _money(base_price)
    if base <= 0:
        raise ValueError(f"课酬金额({base_price})无效，请检查文本中的薪资信息是否正确")
    weekly = max(1, int(weekly_frequency or 1))

    weekly_total = base * weekly
    total_info_fee = _money(weekly_total * _rate_for(weekly))

    if total_info_fee < DEPOSIT:
        raise ValueError(
            f"信息费 ¥{total_info_fee} 低于最低定金 ¥{DEPOSIT}，课酬({base_price})可能过低"
        )

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
    试课失败退费精算（接单规则 2026-10-27 版）：

        退费金额 = max(0, 信息费 − 收到的试课费用 × 0.5)

    试课无费用（收到的费用为 0）则信息费全退；试课成功或教员违约退 0。
    """
    if is_teacher_violated or is_trial_success:
        return Decimal("0.00")

    refund_amount = _money(total_info_fee_paid) - _money(
        _money(trial_paid_by_parent) * Decimal("0.5")
    )
    return max(Decimal("0.00"), refund_amount)
