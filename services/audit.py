"""
资金操作审计写入（PLAN P2-6）。

与 financial_records.operator_role 互补：流水记录"钱怎么动"，审计记录"谁、何时、
从哪个 IP 动的"。写审计失败只记日志不阻断业务——资金主路径的可靠性优先，
审计缺口可由应用日志（WARNING）追溯。
"""
import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import AuditLog

logger = logging.getLogger(__name__)

# 动作枚举：与路由写路径一一对应
ACTION_CONFIRM_DEPOSIT = "confirm_deposit"
ACTION_CONFIRM_BALANCE = "confirm_balance"
ACTION_TRIAL_FAILED = "trial_failed"
ACTION_FORFEIT = "forfeit"
ACTION_CANCEL = "cancel"


def client_ip_from(request: Request | None) -> str | None:
    """取真实客户端 IP：生产经 nginx（覆写 X-Real-IP），本地回退 socket 地址。"""
    if request is None:
        return None
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()[:45]
    return request.client.host if request.client else None


async def record_audit(
    db: AsyncSession,
    *,
    actor_role: str,
    actor_id: int,
    action: str,
    object_id: int,
    tenant_id: int | None = None,
    object_type: str = "application",
    request: Request | None = None,
) -> None:
    """追加一条审计记录。随业务事务 flush，不单独 commit。"""
    try:
        db.add(AuditLog(
            tenant_id=tenant_id,
            actor_role=actor_role,
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            ip=client_ip_from(request),
        ))
        await db.flush()
    except Exception:
        logger.exception("审计日志写入失败 action=%s object=%s/%s", action, object_type, object_id)
