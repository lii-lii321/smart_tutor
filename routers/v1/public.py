"""
公开接口：中介橱窗地图数据（无需登录）。
"""
import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.domain import Order, OrderStatus, Tenant
from models.schemas import AgentBoardResponse, OrderBrief
from services import serializers
from services.geo import ensure_geo_cache, query_all_active
from services.order_maintenance import board_cache_key, get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/public", tags=["公开接口"])

# 橱窗响应缓存：无登录接口，地图自动刷新的突发流量不直打 MySQL；写路径已挂失效钩子
BOARD_CACHE_TTL_SECONDS = 30


def _build_order_brief(order: Order) -> OrderBrief:
    """字段映射单点在 services/serializers.py；公开橱窗始终脱敏。"""
    return OrderBrief.model_validate(serializers.order_board_payload(order))


async def _build_board_response(tenant: Tenant, db) -> AgentBoardResponse:
    geo_orders = []
    try:
        redis = await get_redis_client()
        await ensure_geo_cache(tenant.id, db, redis)
        geo_orders = await query_all_active(tenant.id, redis)
    except Exception:
        # Redis 不可用时降级直查 MySQL，但必须留下日志，避免静默故障无人知晓；
        # 客户端为模块级单例，连接由连接池管理，无需在此关闭
        logger.warning("agent_board redis geo unavailable, fallback to db", exc_info=True)

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
            contact_wechat=tenant.contact_wechat,
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
        contact_wechat=tenant.contact_wechat,
        orders=orders,
    )


@router.get("/agent/{invite_code}/board", response_model=AgentBoardResponse)
async def agent_board(invite_code: str, db: AsyncSession = Depends(get_db)):
    """
    C 端橱窗地图数据。
    根据中介邀请码返回该中介下所有活跃订单的空间坐标。
    无需登录。响应按租户缓存 30s；订单写路径（导入/流转/归档）已挂失效钩子。
    """
    result = await db.execute(select(Tenant).where(Tenant.invite_code == invite_code))
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=404, detail="中介不存在或邀请码无效")

    cached = None
    try:
        redis = await get_redis_client()
        cached = await redis.get(board_cache_key(tenant.id))
    except Exception:
        logger.warning("agent_board cache read unavailable", exc_info=True)

    if cached:
        return AgentBoardResponse.model_validate_json(cached)

    response = await _build_board_response(tenant, db)

    try:
        redis = await get_redis_client()
        await redis.set(board_cache_key(tenant.id), response.model_dump_json(), ex=BOARD_CACHE_TTL_SECONDS)
    except Exception:
        pass

    return response
