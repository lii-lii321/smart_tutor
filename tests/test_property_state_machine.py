"""订单状态机的 property-based 测试：全域 (current, target, role) 组合行为有界。"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from models.domain import OrderStatus
from utils.state_machine import (
    ALLOWED_TRANSITIONS,
    ROLE_TRANSITION_PERMISSIONS,
    validate_transition,
)

_ALL_STATES = list(OrderStatus)
_ROLES = ["teacher", "tenant_admin", "super_admin", "system", "unknown_role"]
_DEPRECATED_TARGETS = [
    OrderStatus.pending_deposit,
    OrderStatus.pending_approval,
    OrderStatus.pending_balance,
]


@given(
    current=st.sampled_from(_ALL_STATES),
    target=st.sampled_from(_ALL_STATES),
    role=st.sampled_from(_ROLES),
)
@settings(max_examples=200, deadline=None)
def test_transition_never_raises_unexpected_exception(current, target, role):
    """任意组合下 validate_transition 只可能：正常返回 / ValueError / PermissionError。"""
    try:
        validate_transition(current, target, role)
    except (ValueError, PermissionError):
        return
    _assert_transition_allowed(current, target, role)


@given(
    current=st.sampled_from(_ALL_STATES),
    target=st.sampled_from(_DEPRECATED_TARGETS),
    role=st.sampled_from(_ROLES),
)
@settings(max_examples=200, deadline=None)
def test_deprecated_states_never_valid_target(current, target, role):
    """废弃状态（pending_deposit 等）作为目标状态时必须拒绝。"""
    with pytest.raises(ValueError):
        validate_transition(current, target, role)


def _assert_transition_allowed(current: OrderStatus, target: OrderStatus, role: str) -> None:
    """正常返回时，跳转必须同时命中状态白名单与角色权限表（两表一致性的防漂移断言）。"""
    assert target in ALLOWED_TRANSITIONS.get(current, set()), f"{current} → {target} 未入白名单却放行"
    assert target in ROLE_TRANSITION_PERMISSIONS.get(role, set()), f"{role} 无权 {target} 却放行"
