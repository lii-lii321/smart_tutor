from models.domain import OrderStatus

# 合法的状态跳转白名单
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.recruiting:        {OrderStatus.pending_deposit, OrderStatus.archived},
    OrderStatus.pending_deposit:   {OrderStatus.pending_approval, OrderStatus.recruiting},
    OrderStatus.pending_approval:  {OrderStatus.pending_balance, OrderStatus.recruiting},
    OrderStatus.pending_balance:   {OrderStatus.trial_in_progress, OrderStatus.recruiting},
    OrderStatus.trial_in_progress: {OrderStatus.completed},
    OrderStatus.completed:         set(),
    OrderStatus.archived:          set(),
}

# 每个角色允许触发的目标状态
ROLE_TRANSITION_PERMISSIONS: dict[str, set[OrderStatus]] = {
    "teacher":      {OrderStatus.pending_approval, OrderStatus.trial_in_progress, OrderStatus.recruiting},
    "tenant_admin": {OrderStatus.pending_deposit, OrderStatus.pending_balance, OrderStatus.completed, OrderStatus.archived, OrderStatus.recruiting},
    "system":       {OrderStatus.archived},
}


def validate_transition(current: OrderStatus, target: OrderStatus, role: str) -> None:
    """校验状态流转合法性。不合法时抛出 ValueError。"""
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"非法状态跳转: {current.value} → {target.value}")
    permitted = ROLE_TRANSITION_PERMISSIONS.get(role, set())
    if target not in permitted:
        raise PermissionError(f"角色 '{role}' 无权触发状态: {target.value}")
