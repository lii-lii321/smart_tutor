import asyncio
import contextlib
import logging

from database import _get_sessionmaker
from services.order_maintenance import (
    archive_expired_recruiting_orders,
    get_redis_client,
    notify_expiring_orders,
)

logger = logging.getLogger(__name__)

# 多 worker 共享的调度锁：TTL 必须小于轮询间隔，避免 worker 崩溃后锁死下一轮
_LOCK_KEY = "smart_tutor:scheduler:order_maintenance"


async def expired_order_cleanup_loop(interval_seconds: int = 300) -> None:
    while True:
        try:
            if not await _acquire_schedule_lock(ttl_seconds=interval_seconds - 60):
                # 其他 worker 已在本轮执行，跳过，避免重复归档/重复通知
                await asyncio.sleep(interval_seconds)
                continue
            sessionmaker = _get_sessionmaker()
            async with sessionmaker() as session:
                await archive_expired_recruiting_orders(session)
                await notify_expiring_orders(session)
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            # 调度任务失败不应拖垮应用，但要留痕排查
            logger.exception("scheduled order maintenance failed")
        await asyncio.sleep(interval_seconds)


async def _acquire_schedule_lock(ttl_seconds: int) -> bool:
    try:
        redis = await get_redis_client()
        return bool(await redis.set(_LOCK_KEY, "1", nx=True, ex=ttl_seconds))
    except Exception:
        # Redis 不可用时退回每进程各自执行，与限流的降级策略一致
        return True


async def stop_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


if __name__ == "__main__":
    # 独立调度容器入口：python -m services.scheduler
    # 调度循环自身吞掉所有异常（只留日志），Sentry 的 logging 集成作为上报通道：
    # logger.exception 的 ERROR 记录会自动成为事件
    from config import settings

    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment="development" if settings.DEV_MODE else "production",
            release=f"{settings.PROJECT_NAME}@{settings.VERSION}",
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    asyncio.run(expired_order_cleanup_loop())
