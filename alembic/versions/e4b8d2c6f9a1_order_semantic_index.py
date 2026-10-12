"""order semantic index (阶段 2)

创建 order_semantic_index：一单一向量的"相似订单"检索索引。纯新增表、
无存量数据回填（历史数据由 scripts/backfill_order_semantic.py 按需回填）。

Revision ID: e4b8d2c6f9a1
Revises: d1c5f9a3e7b2
Create Date: 2026-10-12

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b8d2c6f9a1"
down_revision: Union[str, Sequence[str], None] = "d1c5f9a3e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_semantic_index",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column(
            "synced_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("order_id"),
    )
    op.create_index("idx_osi_tenant", "order_semantic_index", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_osi_tenant", table_name="order_semantic_index")
    op.drop_table("order_semantic_index")
