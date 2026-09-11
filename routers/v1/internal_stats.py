"""
平台内部运营统计（PLAN P2-5 降级方案）：超管鉴权 + 分组聚合一站式返回。

仅做数据库聚合（无时序指标、无耗时分布）——若后续接入 Prometheus +
prometheus-fastapi-instrumentator，本接口仍可作为业务维度的补充口径。
"""
import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import require_role
from models.domain import (
    Application,
    ApplicationStatus,
    AuditLog,
    FinancialRecord,
    FinancialType,
    Order,
    OrderStatus,
    Teacher,
    Tenant,
)
from models.schemas import InternalStatsResponse

router = APIRouter(prefix="/api/v1/internal/stats", tags=["内部统计"])

_ORDER_STATUSES = list(OrderStatus)
_APP_STATUSES = list(ApplicationStatus)
_FIN_TYPES = list(FinancialType)


@router.get("", response_model=InternalStatsResponse)
async def internal_stats(
    payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """超管运营统计：租户/教员/订单/投递/资金/审计六大维度分组聚合。"""
    now = datetime.datetime.utcnow()

    tenant_total = (await db.execute(select(func.count()).select_from(Tenant))).scalar_one()
    tenant_active = (await db.execute(
        select(func.count()).select_from(Tenant).where(Tenant.is_active.is_(True))
    )).scalar_one()
    teacher_total = (await db.execute(select(func.count()).select_from(Teacher))).scalar_one()
    teacher_banned = (await db.execute(
        select(func.count()).select_from(Teacher).where(Teacher.is_banned.is_(True))
    )).scalar_one()

    order_rows = (await db.execute(
        select(Order.status, func.count()).group_by(Order.status)
    )).all()
    order_counts = {status.value: count for status, count in order_rows}

    app_rows = (await db.execute(
        select(Application.status, func.count()).group_by(Application.status)
    )).all()
    app_counts = {status.value: count for status, count in app_rows}

    fin_rows = (await db.execute(
        select(FinancialRecord.type, func.coalesce(func.sum(FinancialRecord.amount), 0.0))
        .group_by(FinancialRecord.type)
    )).all()
    fin_totals = {f_type.value: float(total) for f_type, total in fin_rows}

    audit_total = (await db.execute(select(func.count()).select_from(AuditLog))).scalar_one()
    audit_24h_rows = (await db.execute(
        select(AuditLog.action, AuditLog.actor_role, func.count())
        .where(AuditLog.created_at >= now - datetime.timedelta(hours=24))
        .group_by(AuditLog.action, AuditLog.actor_role)
    )).all()

    by_action: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for action, role, count in audit_24h_rows:
        by_action[action] = by_action.get(action, 0) + count
        by_role[role] = by_role.get(role, 0) + count

    return InternalStatsResponse(
        generated_at=now,
        tenants={"total": tenant_total, "active": tenant_active},
        teachers={"total": teacher_total, "banned": teacher_banned},
        orders={s.value: order_counts.get(s.value, 0) for s in _ORDER_STATUSES},
        applications={s.value: app_counts.get(s.value, 0) for s in _APP_STATUSES},
        finance={
            t.value: fin_totals.get(t.value, 0.0) for t in _FIN_TYPES
        } | {
            "net_amount": (
                fin_totals.get("deposit_in", 0.0)
                + fin_totals.get("balance_in", 0.0)
                - fin_totals.get("refund_out", 0.0)
            )
        },
        audit={"total": audit_total, "last_24h_by_action": by_action, "last_24h_by_role": by_role},
    )
