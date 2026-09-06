import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.domain import Application, ApplicationStatus, Notification, Order, OrderStatus
from services.geo import remove_from_redis


_redis_client = None


async def get_redis_client():
    """
    模块级单例客户端（内含连接池）：避免每个请求重复建连。
    调用方不再 aclose，连接由连接池统一管理。
    """
    global _redis_client
    if _redis_client is None:
        from redis.asyncio import Redis as AsyncRedis
        from redis.backoff import NoBackoff
        from redis.retry import Retry

        # 短连接/读写超时且不重试：Redis 不可用时约 0.5 秒内快速失败降级，
        # 避免默认连接超时叠加重试（可达 3 秒以上）拖慢橱窗与地图
        _redis_client = AsyncRedis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=1.0,
            retry=Retry(NoBackoff(), 0),
            retry_on_error=[],
        )
    return _redis_client


_PAID_TRIAL_APPLICATION_STATUSES = (
    ApplicationStatus.deposit_paid,
    ApplicationStatus.trial_in_progress,
    ApplicationStatus.balance_paid,
)


async def archive_expired_recruiting_orders(
    db: AsyncSession,
    tenant_id: int | None = None,
) -> int:
    now = datetime.datetime.utcnow()
    query = select(Order).where(
        Order.status == OrderStatus.recruiting,
        Order.expired_at <= now,
        # 仍有已收款/试课中投递的订单不能自动归档，否则教员已付定金随订单一起悬空
        ~exists(
            select(Application.id).where(
                Application.order_id == Order.id,
                Application.status.in_(_PAID_TRIAL_APPLICATION_STATUSES),
            )
        ),
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

    await db.flush()
    return len(orders)


async def notify_expiring_orders(
    db: AsyncSession,
    hours_ahead: int = 24,
) -> int:
    """
    招聘中的订单距过期不足 hours_ahead 小时时提醒租户（每单只提醒一次，
    以是否存在同单同标题的通知为准）。
    """
    now = datetime.datetime.utcnow()
    deadline = now + datetime.timedelta(hours=hours_ahead)
    query = select(Order).where(
        Order.status == OrderStatus.recruiting,
        Order.expired_at > now,
        Order.expired_at <= deadline,
    )
    result = await db.execute(query)
    orders = result.scalars().all()
    if not orders:
        return 0

    order_ids = [order.id for order in orders]
    notified_result = await db.execute(
        select(Notification.order_id).where(
            Notification.order_id.in_(order_ids),
            Notification.title == "订单即将过期",
        )
    )
    already_notified = {row[0] for row in notified_result.all()}

    created = 0
    for order in orders:
        if order.id in already_notified:
            continue
        remaining_hours = max(1, int((order.expired_at - now).total_seconds() // 3600))
        db.add(Notification(
            tenant_id=order.tenant_id,
            title="订单即将过期",
            content=f"「{order.grade_subject}」将在约 {remaining_hours} 小时后过期下架，"
                    "如需继续招聘请重新发布刷新有效期。",
            order_id=order.id,
        ))
        created += 1

    if created:
        await db.flush()
    return created
