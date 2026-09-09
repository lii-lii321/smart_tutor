"""
SQLite → MySQL 一次性数据搬迁脚本。

用法（在项目根目录）：
    1. 先对目标库执行 Alembic 迁移：alembic upgrade head
    2. 设置源/目标连接串并运行：
       set SOURCE_DATABASE_URL=sqlite+aiosqlite:///dev.db
       set DATABASE_URL=mysql+aiomysql://user:pass@host:3306/smart_tutor?charset=utf8mb4
       python scripts/migrate_sqlite_to_mysql.py

行为：
    - 按 FK 依赖顺序搬迁 tenants → teachers → teacher_resumes → orders
      → applications → financial_records → notifications；
    - 保留原主键 ID，MySQL 自增计数随最大 ID 自然延续；
    - 目标表必须为空（防止重复搬迁造成主键冲突），确认覆盖时加 --overwrite；
    - 全程单事务，任何一步失败整体回滚，不会留下半截数据。

注意：目标库连接串请勿指向生产库执行演练之外的操作。
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

import database as database_mod  # noqa: E402

# 搬迁顺序即 FK 依赖顺序；覆盖清空时按相反顺序
TABLES = [
    "tenants",
    "teachers",
    "teacher_resumes",
    "orders",
    "applications",
    "financial_records",
    "notifications",
]


async def main(overwrite: bool) -> None:
    source_url = os.environ.get("SOURCE_DATABASE_URL") or "sqlite+aiosqlite:///dev.db"
    target_url = database_mod.settings.DATABASE_URL
    if not target_url or target_url.startswith("sqlite"):
        print("错误：DATABASE_URL 未指向 MySQL。请在环境变量中配置目标库连接串。")
        sys.exit(1)

    from sqlalchemy import create_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    source_engine = create_async_engine(source_url)
    target_engine = create_async_engine(
        target_url,
        pool_pre_ping=True,
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )
    target_sessionmaker = async_sessionmaker(target_engine, class_=AsyncSession, expire_on_commit=False)

    async with source_engine.connect() as source_conn:
        tables_data: dict[str, list[dict]] = {}
        for table in TABLES:
            result = await source_conn.execute(text(f"SELECT * FROM {table}"))
            columns = list(result.keys())
            tables_data[table] = [dict(zip(columns, row, strict=False)) for row in result.all()]

    async with target_sessionmaker() as session:
        result = await session.execute(text("SHOW TABLES"))
        existing = {row[0] for row in result.all()}
        missing = [table for table in TABLES if table not in existing]
        if missing:
            print(f"错误：目标库缺少表 {missing}，请先执行 alembic upgrade head。")
            sys.exit(1)

        for table in TABLES:
            count = await session.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            if count and not overwrite:
                print(f"错误：目标表 {table} 已有 {count} 行。确认覆盖请加 --overwrite。")
                sys.exit(1)

        if overwrite:
            for table in reversed(TABLES):
                await session.execute(text(f"DELETE FROM {table}"))

        for table in TABLES:
            rows = tables_data[table]
            if not rows:
                print(f"[OK] {table}: 0 行")
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join(f":{col}" for col in columns)
            column_list = ", ".join(columns)
            batch_size = 500
            for i in range(0, len(rows), batch_size):
                await session.execute(
                    text(f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"),
                    rows[i:i + batch_size],
                )
            print(f"[OK] {table}: {len(rows)} 行")

        await session.commit()

    await source_engine.dispose()
    await target_engine.dispose()
    print("\n=== 搬迁完成，请抽查行数与业务数据后切换应用连接 ===")


if __name__ == "__main__":
    asyncio.run(main("--overwrite" in sys.argv))
