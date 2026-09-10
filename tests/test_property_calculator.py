"""精算恒等式的 property-based 测试：任意合法输入下输出结构恒成立。"""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from services.calculator import DEPOSIT, calculate_info_fee

_MIN_BASE = Decimal("0.01")
_MAX_BASE = Decimal("999999")
# 0.8 是最低费率：base >= 125.00 时任何频次下 total >= 100 定金，calculate 必成功
_SAFE_MIN_BASE = Decimal("125.00")


@given(
    base_price=st.decimals(min_value=_SAFE_MIN_BASE, max_value=_MAX_BASE, places=2),
    weekly_frequency=st.integers(min_value=1, max_value=10),
    is_summer_vacation=st.booleans(),
)
@settings(max_examples=200, deadline=None)
def test_info_fee_invariants_for_any_valid_base_price(base_price, weekly_frequency, is_summer_vacation):
    """合法课酬（必成区）下：三个金额均为两位小数 Decimal、deposit+balance==total、total>=定金。"""
    result = calculate_info_fee(base_price, weekly_frequency, is_summer_vacation)

    total = result["total_info_fee"]
    deposit = result["deposit"]
    balance = result["balance"]

    for amount in (total, deposit, balance):
        assert isinstance(amount, Decimal)
        assert amount.as_tuple().exponent == -2

    assert deposit + balance == total
    assert total >= DEPOSIT
    assert deposit == DEPOSIT
    assert balance >= 0


@given(
    base_price=st.decimals(min_value=_MIN_BASE, max_value=_MAX_BASE, places=2),
    weekly_frequency=st.integers(min_value=1, max_value=10),
    is_summer_vacation=st.booleans(),
)
@settings(max_examples=200, deadline=None)
def test_low_price_either_rejected_or_satisfies_invariants(base_price, weekly_frequency, is_summer_vacation):
    """全域结果有界：低价课酬要么以「低于最低定金」拒绝，要么输出满足恒等式。"""
    try:
        result = calculate_info_fee(base_price, weekly_frequency, is_summer_vacation)
    except ValueError as e:
        assert "低于最低定金" in str(e)
        return
    assert result["deposit"] + result["balance"] == result["total_info_fee"]
    assert result["total_info_fee"] >= DEPOSIT


@given(
    base_price=st.one_of(
        st.decimals(min_value=Decimal("-999999"), max_value=Decimal("0.00"), places=2),
        st.integers(min_value=-999999, max_value=0),
    ),
    weekly_frequency=st.integers(min_value=1, max_value=10),
    is_summer_vacation=st.booleans(),
)
@settings(max_examples=100, deadline=None)
def test_non_positive_base_price_always_raises_value_error(base_price, weekly_frequency, is_summer_vacation):
    """课酬 <= 0 时必须拒绝（以 ValueError 形式），而非产出金额。"""
    try:
        calculate_info_fee(base_price, weekly_frequency, is_summer_vacation)
    except ValueError:
        return
    raise AssertionError(f"base_price={base_price!r} 未被拒绝")


@given(base_price=st.decimals(min_value=_MIN_BASE, max_value=Decimal("66.66"), places=2))
@settings(max_examples=50, deadline=None)
def test_low_price_below_deposit_rejected_with_value_error(base_price):
    """base <= 66.66 时 1.5 倍信息费（最高常规费率）舍入后仍 < 100 定金，必报错。"""
    try:
        calculate_info_fee(base_price, 1, False)
    except ValueError as e:
        assert "低于最低定金" in str(e)
        return
    raise AssertionError(f"低价课酬 {base_price} 未触发定金下限校验")
