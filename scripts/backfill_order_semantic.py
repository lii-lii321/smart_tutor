"""全量回填订单语义索引（阶段 2）。

用法：
    python -m scripts.backfill_order_semantic            # 全量回填
    python -m scripts.backfill_order_semantic --limit 32 # 每批条数（默认 32）

说明：只回填「招聘中且缺索引」的订单——与调度兜底同一查询口径；
Embedding 服务不可用时立即退出并提示（重跑即可续传，天然幂等）。
已完成/已归档订单不建索引：相似检索以实时状态复核，历史单按需在阶段 3 扩展。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import _get_sessionmaker  # noqa: E402
from services.order_semantic import backfill_missing  # noqa: E402


async def main(batch_size: int) -> int:
    sessionmaker = _get_sessionmaker()
    total = 0
    while True:
        async with sessionmaker() as session:
            try:
                count = await backfill_missing(session, limit=batch_size)
                await session.commit()
            except Exception as exc:
                print(f"回填中断（已同步 {total} 条）：{exc}")
                print("Embedding 服务不可用或网络异常；处理后重跑本脚本可续传。")
                return 1
        if count == 0:
            break
        total += count
        print(f"已同步 {total} 条…")
    print(f"回填完成：共 {total} 条订单建立语义索引。")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="回填订单语义索引")
    parser.add_argument("--limit", type=int, default=32, help="每批同步条数")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.limit)))
