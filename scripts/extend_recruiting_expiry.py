"""
一次性运维脚本：存量「招聘中」订单的有效期按新生命周期口径从今天重新计时
（2026-11-16 生命周期 14 天→30 天，用户要求"从今天开始记"）。

只动 status=recruiting 的订单：试课中/已成交/已归档是历史事实，不续期。
expired_at = now + ORDER_EXPIRE_HOURS；expiry_refreshed_at = now（打标新提醒周期，
临期提醒按周期去重——不打标会把旧周期已发的提醒错当新周期的去重依据）。

用法：
  python scripts/extend_recruiting_expiry.py --url sqlite+aiosqlite:///./dev.db           # 预览
  python scripts/extend_recruiting_expiry.py --url ... --apply                            # 写库
  容器内省略 --url 时自动读 DATABASE_URL 环境变量（生产运维路径）
"""
import argparse
import asyncio
import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine

import models.domain  # noqa: F401
from config import settings
from models.domain import Order, OrderStatus
from utils.clock import utcnow


async def main(url: str, apply: bool, hours: int | None) -> None:
    expire_hours = hours or settings.ORDER_EXPIRE_HOURS
    now = utcnow()
    new_expired_at = now + datetime.timedelta(hours=expire_hours)
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        rows = (await conn.execute(
            select(Order.id, Order.raw_id, Order.expired_at).where(
                Order.status == OrderStatus.recruiting,
            )
        )).all()

        print(f"招聘中订单 {len(rows)} 单，按新生命周期 {expire_hours}h（{expire_hours // 24} 天）从今天重新计时")
        for order_id, raw_id, expired_at in rows[:10]:
            print(f"  - 订单 #{order_id} ({raw_id}): {expired_at} -> {new_expired_at}")
        if len(rows) > 10:
            print(f"  ... 其余 {len(rows) - 10} 单省略")

        if apply and rows:
            result = await conn.execute(
                update(Order)
                .where(Order.status == OrderStatus.recruiting)
                .values(expired_at=new_expired_at, expiry_refreshed_at=now)
            )
            print(f"已写库 {result.rowcount} 单（expired_at={new_expired_at}, expiry_refreshed_at={now}）")
        elif not apply:
            print("（预览模式，未写库；加 --apply 生效）")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="存量招聘中订单有效期从今天重新计时")
    parser.add_argument("--url", default=None, help="缺省读 DATABASE_URL 环境变量（容器内）")
    parser.add_argument("--apply", action="store_true", help="实际写库（默认仅预览）")
    parser.add_argument("--hours", type=int, default=None, help="覆盖有效期小时数（缺省读 config）")
    args = parser.parse_args()
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("未提供 --url，且环境变量 DATABASE_URL 不存在")
    sys.exit(asyncio.run(main(url, args.apply, args.hours)))
