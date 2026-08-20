"""
Redis GEO 服务：空间索引读写 + MySQL 惰性重建。
"""
import datetime
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models.domain import Order, OrderStatus

GEO_KEY_PREFIX = "smart_tutor:orders:geo"
ORDER_EXPIRE_SECONDS = settings.ORDER_EXPIRE_HOURS * 3600


def _geo_key(tenant_id: int) -> str:
    return f"{GEO_KEY_PREFIX}:{tenant_id}"


async def batch_sync_to_redis(orders: list[Order], redis: Redis) -> None:
    """批量写入订单坐标到 Redis GEO。"""
    pipe = redis.pipeline()
    for order in orders:
        key = _geo_key(order.tenant_id)
        lng = float(order.lng)
        lat = float(order.lat)
        pipe.geoadd(key, (lng, lat, str(order.id)))
    # 整个 tenant 的 key 设 TTL
    if orders:
        pipe.expire(_geo_key(orders[0].tenant_id), ORDER_EXPIRE_SECONDS)
    await pipe.execute()


async def remove_from_redis(tenant_id: int, order_id: int, redis: Redis) -> None:
    """从 Redis GEO 中移除单个订单。"""
    await redis.zrem(_geo_key(tenant_id), str(order_id))


async def query_all_active(
    tenant_id: int, redis: Redis
) -> list[dict]:
    """
    获取某租户下的所有活跃订单坐标。
    返回 [{"order_id": ..., "lng": ..., "lat": ...}, ...]
    """
    key = _geo_key(tenant_id)
    # GEOADD 存入时用 order_id 作为 member，
    # 需要用 GEOPOS 取坐标，或直接 ZRANGE + GEOPOS
    members = await redis.zrange(key, 0, -1)
    if not members:
        return []

    pipe = redis.pipeline()
    for m in members:
        pipe.geopos(key, m)
    positions = await pipe.execute()

    results = []
    for member, pos in zip(members, positions):
        if pos and pos[0] is not None:
            results.append({
                "order_id": int(member),
                "lng": pos[0],
                "lat": pos[1],
            })
    return results


async def ensure_geo_cache(
    tenant_id: int, db: AsyncSession, redis: Redis
) -> None:
    """惰性检查：如果 Redis GEO key 不存在，从 MySQL 重建。"""
    key = _geo_key(tenant_id)
    exists = await redis.exists(key)
    if exists:
        return

    now = datetime.datetime.utcnow()
    result = await db.execute(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.status == OrderStatus.recruiting,
            Order.expired_at > now,
        )
    )
    active_orders = result.scalars().all()
    if active_orders:
        pipe = redis.pipeline()
        for order in active_orders:
            pipe.geoadd(key, (float(order.lng), float(order.lat), str(order.id)))
        pipe.expire(key, ORDER_EXPIRE_SECONDS)
        await pipe.execute()
