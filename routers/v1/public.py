"""
公开接口：中介橱窗地图数据（无需登录）。
"""
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.domain import Tenant, Order, OrderStatus
from models.schemas import AgentBoardResponse, OrderBrief
from services.geo import ensure_geo_cache, query_all_active
from config import settings

router = APIRouter(prefix="/api/v1/public", tags=["公开接口"])


def _build_order_brief(order: Order) -> OrderBrief:
    return OrderBrief.model_validate(
        {
            "id": order.id,
            "grade_subject": order.grade_subject,
            "price_total": order.price_total,
            "base_price": float(order.base_price),
            "weekly_frequency": order.weekly_frequency,
            "fuzzy_address": order.fuzzy_address,
            "subway_remark": order.subway_remark,
            "lng": float(order.lng),
            "lat": float(order.lat),
            "calculated_info_fee": float(order.calculated_info_fee),
            "deposit_amount": float(order.deposit_amount),
            "balance_amount": float(order.balance_amount),
            "needs_manual_price": float(order.base_price) <= 0,
            "created_at": order.created_at,
        }
    )


@router.get("/agent/{invite_code}/board", response_model=AgentBoardResponse)
async def agent_board(invite_code: str, db: AsyncSession = Depends(get_db)):
    """
    C 端橱窗地图数据。
    根据中介邀请码返回该中介下所有活跃订单的空间坐标。
    无需登录。
    """
    result = await db.execute(select(Tenant).where(Tenant.invite_code == invite_code))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="中介不存在或邀请码无效")

    geo_orders = []
    try:
        from redis.asyncio import Redis as AsyncRedis
        redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
        await ensure_geo_cache(tenant.id, db, redis)
        geo_orders = await query_all_active(tenant.id, redis)
        await redis.aclose()
    except Exception:
        pass

    if not geo_orders:
        now = datetime.datetime.utcnow()
        result = await db.execute(
            select(Order).where(
                Order.tenant_id == tenant.id,
                Order.status == OrderStatus.recruiting,
                Order.expired_at > now,
            ).order_by(Order.created_at.desc())
        )
        mysql_orders = result.scalars().all()
        return AgentBoardResponse(
            tenant_name=tenant.tenant_name,
            invite_code=tenant.invite_code,
            orders=[_build_order_brief(o) for o in mysql_orders],
        )

    order_ids = [g["order_id"] for g in geo_orders]
    if order_ids:
        now = datetime.datetime.utcnow()
        result = await db.execute(
            select(Order).where(
                Order.id.in_(order_ids),
                Order.status == OrderStatus.recruiting,
                Order.expired_at > now,
            )
        )
        full_orders = {o.id: o for o in result.scalars().all()}
    else:
        full_orders = {}

    orders = []
    for geo in geo_orders:
        oid = geo["order_id"]
        if oid in full_orders:
            orders.append(_build_order_brief(full_orders[oid]))

    return AgentBoardResponse(
        tenant_name=tenant.tenant_name,
        invite_code=tenant.invite_code,
        orders=orders,
    )
