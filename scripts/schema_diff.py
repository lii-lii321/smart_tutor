"""
P2-1 前置工具：对账目标库 schema 与当前 models 的差异（只读，不改库）。

用途：
  1. 退役 database.py `_ensure_*` 前，证明目标库与迁移链一致（diff 为空才可退役）；
  2. 长期开发库（dev.db）/ 生产 MySQL 的周期性对账。

用法：
  python scripts/schema_diff.py --url "mysql+aiomysql://user:pass@127.0.0.1:3306/smart_tutor?charset=utf8mb4"
  python scripts/schema_diff.py --url "sqlite+aiosqlite:///./dev.db"

退出码：无差异=0；有差异=1（可接入 CI/脚本判断）。
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

import models.domain  # noqa: F401  必须先导入：把所有表注册进 Base.metadata
from database import Base


async def main(url: str) -> int:
    # 复用项目统一的 async 驱动（aiomysql / aiosqlite），不额外引入同步驱动
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        diffs = await conn.run_sync(
            lambda sync_conn: compare_metadata(MigrationContext.configure(sync_conn), Base.metadata)
        )
    await engine.dispose()

    if not diffs:
        print("schema_diff: 无差异，目标库与 models 一致")
        return 0

    print(f"schema_diff: 发现 {len(diffs)} 处差异")
    for diff in diffs:
        print(f"  - {diff}")
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="目标库 vs models 的 schema 对账（只读）")
    parser.add_argument("--url", required=True, help="数据库 URL（mysql+aiomysql:// 或 sqlite+aiosqlite://）")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url)))
