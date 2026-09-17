import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.domain import Application, ApplicationStatus, Notification, Order, OrderStatus
from services.geo import remove_from_redis

_redis_client = None


def board_cache_key(tenant_id: int) -> str:
    return f"smart_tutor:board:{tenant_id}"


async def invalidate_board_cache(*tenant_ids: int | None) -> None:
    """
    订单写路径调用：橱窗 30s 响应缓存的失效钩子。
    Redis 不可用时静默跳过——失效失败只会让橱窗最多多展示 30 秒旧数据（TTL 兜底）。
    """
    ids = {tid for tid in tenant_ids if tid is not None}
    if not ids:
        return
    try:
        redis = await get_redis_client()
        await redis.delete(*(board_cache_key(tid) for tid in ids))
    except Exception:
        pass


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


def refresh_order_expiry(order: Order, now: datetime.datetime) -> None:
    """
    重开招聘统一的有效期策略（原 orders.py / applications.py 各一份的
    _refresh_order_expiry 收敛到此单点）：从现在起重新计时，
    并写周期标记——临期提醒按 expiry_refreshed_at 划分"本周期"去重。
    """
    order.expired_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)
    order.expiry_refreshed_at = now


_PAID_TRIAL_APPLICATION_STATUSES = (
    ApplicationStatus.deposit_paid,
    ApplicationStatus.trial_in_progress,
    ApplicationStatus.balance_paid,
)


async def archive_expired_recruiting_orders(db: AsyncSession) -> list[tuple[int, int]]:
    """
    归档过期招聘中订单，返回本次归档的 (tenant_id, order_id) 列表。

    并发正确性（2026-09 审计：原实现无锁读 + 无条件 ORM 覆写，会把已收定金的订单归档、
    或把管理员刚重开的订单盖回 archived）：
    - FOR UPDATE 锁定候选订单行（MySQL 生效）：与资金端点"先锁订单行"全局同序不死锁，
      持锁期间评估"无已收款投递"守卫，confirm-deposit 与归档不再互相穿透；
    - 逐条条件更新（WHERE status=recruiting AND expired_at<=now）+ rowcount 判定，
      SQLite（FOR UPDATE 失效）下同样不会覆盖已重开/已流转的订单；
    - 只取 id/tenant_id 两列：不再加载 raw_text 大字段，backlog 大时也不拖长事务。
    Redis 地图索引清理由调用方在 commit 之后执行（remove_archived_from_redis）。
    """
    now = datetime.datetime.utcnow()
    query = select(Order.id, Order.tenant_id).where(
        Order.status == OrderStatus.recruiting,
        Order.expired_at <= now,
        # 仍有已收款/试课中投递的订单不能自动归档，否则教员已付定金随订单一起悬空
        ~exists(
            select(Application.id).where(
                Application.order_id == Order.id,
                Application.status.in_(_PAID_TRIAL_APPLICATION_STATUSES),
            )
        ),
    ).with_for_update()
    candidates = (await db.execute(query)).all()

    archived: list[tuple[int, int]] = []
    for order_id, tenant_id in candidates:
        row = await db.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status == OrderStatus.recruiting,
                Order.expired_at <= now,
            )
            .values(status=OrderStatus.archived)
        )
        if row.rowcount == 1:
            archived.append((tenant_id, order_id))
    await db.flush()
    return archived


async def remove_archived_from_redis(archived: list[tuple[int, int]]) -> None:
    """归档 commit 之后的 Redis 收尾：移除地图索引 + 失效橱窗缓存。
    必须在 DB 提交后调用——回滚时不能把仍招聘中的订单从地图上抹掉。"""
    if not archived:
        return
    try:
        redis = await get_redis_client()
        for tenant_id, order_id in archived:
            await remove_from_redis(tenant_id, order_id, redis)
    except Exception:
        pass
    await invalidate_board_cache(*(tenant_id for tenant_id, _ in archived))


async def notify_expiring_orders(
    db: AsyncSession,
    hours_ahead: int = 24,
) -> int:
    """
    招聘中的订单距过期不足 hours_ahead 小时时提醒租户。

    以「本周期」去重：周期起点优先取持久化标记 order.expiry_refreshed_at
    （重开招聘与 PATCH 改有效期时写入）；存量行无标记时回退按
    expired_at − 有效期 推算。旧周期的提醒 created_at 早于起点，不再压制新提醒。
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
        select(Notification.order_id, Notification.created_at).where(
            Notification.order_id.in_(order_ids),
            Notification.title == "订单即将过期",
        )
    )
    # 本周期起点（naive UTC，与 created_at 同口径）；跨方言在 Python 侧比较，避免日期函数差异
    cycle_start = {
        order.id: (
            order.expiry_refreshed_at
            or order.expired_at - datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)
        )
        for order in orders
    }
    already_notified = {
        row[0]
        for row in notified_result.all()
        if row[1] is not None and row[1] >= cycle_start[row[0]]
    }

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
