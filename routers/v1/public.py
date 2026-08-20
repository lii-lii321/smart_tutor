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


@router.get("/agent/{invite_code}/board", response_model=AgentBoardResponse)
async def agent_board(invite_code: str, db: AsyncSession = Depends(get_db)):
    """
    C 端橱窗地图数据。
    根据中介邀请码返回该中介下所有活跃订单的空间坐标。
    无需登录。
    """
    # 查租户
    result = await db.execute(
        select(Tenant).where(Tenant.invite_code == invite_code)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="中介不存在或邀请码无效")

    # 优先从 Redis GEO 查询，失败则降级到 MySQL
    geo_orders = []
    try:
        from redis.asyncio import Redis as AsyncRedis
        redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
        await ensure_geo_cache(tenant.id, db, redis)
        geo_orders = await query_all_active(tenant.id, redis)
        await redis.aclose()
    except Exception:
        pass

    # 降级：MySQL 直接查
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
            orders=[
                OrderBrief(
                    id=o.id,
                    grade_subject=o.grade_subject,
                    price_total=o.price_total,
                    base_price=float(o.base_price),
                    weekly_frequency=o.weekly_frequency,
                    fuzzy_address=o.fuzzy_address,
                    subway_remark=o.subway_remark,
                    lng=float(o.lng),
                    lat=float(o.lat),
                    calculated_info_fee=float(o.calculated_info_fee),
                    deposit_amount=float(o.deposit_amount),
                    balance_amount=float(o.balance_amount),
                    needs_manual_price=float(o.base_price) <= 0,
                    created_at=o.created_at,
                )
                for o in mysql_orders
            ],
        )

    # Redis 返回的是 order_id 列表，需要从 MySQL 补全字段
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
            o = full_orders[oid]
            orders.append(OrderBrief(
                id=o.id,
                grade_subject=o.grade_subject,
                price_total=o.price_total,
                base_price=float(o.base_price),
                weekly_frequency=o.weekly_frequency,
                fuzzy_address=o.fuzzy_address,
                subway_remark=o.subway_remark,
                lng=float(o.lng),
                lat=float(o.lat),
                calculated_info_fee=float(o.calculated_info_fee),
                deposit_amount=float(o.deposit_amount),
                balance_amount=float(o.balance_amount),
                needs_manual_price=float(o.base_price) <= 0,
                created_at=o.created_at,
            ))

    return AgentBoardResponse(
        tenant_name=tenant.tenant_name,
        invite_code=tenant.invite_code,
        orders=orders,
    )
