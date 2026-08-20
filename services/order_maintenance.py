import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.domain import Order, OrderStatus
from services.geo import remove_from_redis


async def get_redis_client():
    from redis.asyncio import Redis as AsyncRedis

    return AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)


async def archive_expired_recruiting_orders(
    db: AsyncSession,
    tenant_id: int | None = None,
) -> int:
    now = datetime.datetime.utcnow()
    query = select(Order).where(
        Order.status == OrderStatus.recruiting,
        Order.expired_at <= now,
    )
    if tenant_id is not None:
        query = query.where(Order.tenant_id == tenant_id)

    result = await db.execute(query)
    orders = result.scalars().all()
    if not orders:
        return 0

    redis = None
    try:
        redis = await get_redis_client()
        for order in orders:
            order.status = OrderStatus.archived
            await remove_from_redis(order.tenant_id, order.id, redis)
    except Exception:
        for order in orders:
            order.status = OrderStatus.archived
    finally:
        if redis is not None:
            await redis.aclose()

    await db.flush()
    return len(orders)
