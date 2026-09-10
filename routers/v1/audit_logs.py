"""
资金操作审计查询：超管专享，按租户/动作/时间过滤 + 分页。

写入点在 applications.py 的五个资金写路径（confirm_deposit/confirm_balance/
trial_failed/forfeit/cancel），本路由只读。
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_role
from models.domain import AuditLog
from models.schemas import AuditLogItem, AuditLogListResponse

router = APIRouter(prefix="/api/v1/audit-logs", tags=["审计"])

_ALLOWED_ACTIONS = {
    "confirm_deposit",
    "confirm_balance",
    "trial_failed",
    "forfeit",
    "cancel",
}


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    tenant_id: int | None = None,
    action: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
    payload: TokenPayload = Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """超管查询资金操作审计：谁、何时、从哪个 IP 确认了哪笔资金操作。"""
    if action is not None and action not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail=f"未知动作类型，可选值：{', '.join(sorted(_ALLOWED_ACTIONS))}")

    query = select(AuditLog)
    if tenant_id is not None:
        query = query.where(AuditLog.tenant_id == tenant_id)
    if action is not None:
        query = query.where(AuditLog.action == action)
    if start_date is not None:
        query = query.where(AuditLog.created_at >= start_date)
    if end_date is not None:
        query = query.where(AuditLog.created_at < end_date + datetime.timedelta(days=1))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        await db.execute(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return AuditLogListResponse(
        items=[AuditLogItem.model_validate(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )
