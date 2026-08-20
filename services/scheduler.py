import asyncio
import contextlib

from database import _get_sessionmaker
from services.order_maintenance import archive_expired_recruiting_orders


async def expired_order_cleanup_loop(interval_seconds: int = 300) -> None:
    while True:
        try:
            sessionmaker = _get_sessionmaker()
            async with sessionmaker() as session:
                await archive_expired_recruiting_orders(session)
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)


async def stop_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
