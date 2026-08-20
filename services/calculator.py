"""
精算模块：信息费计算 + 试课退费精算。
"""


def calculate_info_fee(base_price: float, weekly_frequency: int, is_summer_vacation: bool) -> dict:
    """
    根据行业标准计算全额信息费、定金与尾款。

    费率规则：
        - 寒暑假单：2.5 倍单次课酬
        - 一周 1 次：1.5 倍
        - 一周 2 次：1.0 倍
        - 一周 3 次：0.9 倍
        - 一周 4 次及以上：0.8 倍
    """
    DEPOSIT = 100.0

    if is_summer_vacation:
        rate = 2.5
    elif weekly_frequency == 1:
        rate = 1.5
    elif weekly_frequency == 2:
        rate = 1.0
    elif weekly_frequency == 3:
        rate = 0.9
    else:
        rate = 0.8

    if base_price <= 0:
        raise ValueError(f"课酬金额({base_price})无效，请检查文本中的薪资信息是否正确")

    total_info_fee = round(base_price * rate, 2)

    if total_info_fee < DEPOSIT:
        raise ValueError(f"信息费 ¥{total_info_fee} 低于最低定金 ¥{DEPOSIT}，课酬({base_price})可能过低")

    balance = round(total_info_fee - DEPOSIT, 2)

    return {
        "total_info_fee": total_info_fee,
        "deposit": DEPOSIT,
        "balance": balance,
    }


def calculate_refund(
    total_info_fee_paid: float,
    trial_paid_by_parent: float,
    is_trial_success: bool,
    is_teacher_violated: bool,
) -> float:
    """
    试课失败退费精算公式：

        退费金额 = max(0, 已交信息费 − 家长支付的试课薪酬 × 70%)

    若试课成功或教员违规，退费金额为 0。
    """
    if is_teacher_violated or is_trial_success:
        return 0.0

    refund_amount = total_info_fee_paid - (trial_paid_by_parent * 0.7)
    return max(0.0, round(refund_amount, 2))
