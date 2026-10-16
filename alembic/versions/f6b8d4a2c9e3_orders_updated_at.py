"""orders.updated_at（行级更新时间）

订单表补 updated_at：语义索引过期检测（synced_at < updated_at 即重嵌）与
后续增量抽取（数仓/ES）的基础设施字段，ORM default/onupdate 维护，
业务代码不手工赋值。存量行回填为当前时间（首次同步后自然被 synced_at 覆盖语义）。

方言分支：SQLite 禁止 ADD COLUMN 携带非常量默认（CURRENT_TIMESTAMP），
先加可空列再以 Core 表达式回填；MySQL 直接带 server_default。迁移只在
MySQL（生产/CI）执行，SQLite 分支服务于本地 alembic 演练。

Revision ID: f6b8d4a2c9e3
Revises: e4b8d2c6f9a1
Create Date: 2026-10-16

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6b8d4a2c9e3"
down_revision: Union[str, Sequence[str], None] = "e4b8d2c6f9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.add_column("orders", sa.Column("updated_at", sa.TIMESTAMP(), nullable=True))
        orders_t = sa.table("orders", sa.column("updated_at", sa.TIMESTAMP()))
        bind.execute(
            orders_t.update()
            .where(orders_t.c.updated_at.is_(None))
            .values(updated_at=sa.func.current_timestamp())
        )
        return
    op.add_column(
        "orders",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
            comment="最近一次更新时间（ORM onupdate 维护）：语义索引过期检测与增量同步依赖",
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "updated_at")
