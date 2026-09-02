from models.domain import OrderStatus

# 合法的状态跳转白名单。
# 注意：订单状态由投递流程驱动（routers/v1/applications.py），
# 这里仅约束 `/orders/{id}/transit` 等通用入口，防止任意跳转。
# 候选/定金阶段不再占用订单状态：订单保持 recruiting 直到开始试课。
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.recruiting: {OrderStatus.archived},
    OrderStatus.trial_in_progress: {OrderStatus.completed, OrderStatus.recruiting, OrderStatus.archived},
    OrderStatus.completed: set(),
    OrderStatus.archived: set(),
    # 废弃状态不可作为任何跳转的目标或来源
    OrderStatus.pending_deposit: set(),
    OrderStatus.pending_approval: set(),
    OrderStatus.pending_balance: set(),
}

# 每个角色允许触发的目标状态。
# teacher 不直接驱动订单状态（只能投递/支付，见 applications 路由）。
ROLE_TRANSITION_PERMISSIONS: dict[str, set[OrderStatus]] = {
    "teacher": set(),
    "tenant_admin": {OrderStatus.recruiting, OrderStatus.archived},
    "super_admin": {OrderStatus.recruiting, OrderStatus.archived},
    "system": {OrderStatus.archived},
}


def validate_transition(current: OrderStatus, target: OrderStatus, role: str) -> None:
    """校验状态流转合法性。不合法时抛出 ValueError / PermissionError。"""
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"非法状态跳转: {current.value} → {target.value}")
    permitted = ROLE_TRANSITION_PERMISSIONS.get(role, set())
    if target not in permitted:
        raise PermissionError(f"角色 '{role}' 无权触发状态: {target.value}")
