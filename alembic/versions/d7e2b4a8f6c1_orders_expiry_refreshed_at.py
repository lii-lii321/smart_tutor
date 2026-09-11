"""orders.expiry_refreshed_at column

Revision ID: d7e2b4a8f6c1
Revises: b2f6d8e4c1a9
Create Date: 2026-09-11

临期提醒周期标记（OPEN-ISSUES §1.1）：记录订单最近一次重开/刷新有效期的时刻，
notify_expiring_orders 按"提醒 created_at >= 该标记"去重，替代按
expired_at − 有效期 推算周期起点；管理端 PATCH 改 expired_at 时同步打标。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7e2b4a8f6c1'
down_revision: Union[str, Sequence[str], None] = 'b2f6d8e4c1a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(
            sa.Column('expiry_refreshed_at', sa.TIMESTAMP(), nullable=True,
                      comment='最近一次重开/刷新有效期的时刻')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_column('expiry_refreshed_at')
