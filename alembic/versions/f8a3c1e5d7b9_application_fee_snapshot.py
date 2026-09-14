"""applications fee snapshot columns

Revision ID: f8a3c1e5d7b9
Revises: d7e2b4a8f6c1
Create Date: 2026-09-13

定金确认时的费率快照（审查 P1-2）：fee_total / fee_deposit / fee_balance 三列
在 confirm_deposit 写入，之后尾款/退款/没收一律读快照——教员付定金后中介改价
不再影响该投递的收款与退款口径。NULL 表示未确认过定金（历史数据回退现算）。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8a3c1e5d7b9'
down_revision: Union[str, Sequence[str], None] = 'd7e2b4a8f6c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('applications') as batch_op:
        batch_op.add_column(
            sa.Column('fee_total', sa.DECIMAL(8, 2), nullable=True,
                      comment='定金确认时的全额信息费快照')
        )
        batch_op.add_column(
            sa.Column('fee_deposit', sa.DECIMAL(8, 2), nullable=True,
                      comment='定金确认时的定金金额快照')
        )
        batch_op.add_column(
            sa.Column('fee_balance', sa.DECIMAL(8, 2), nullable=True,
                      comment='定金确认时的尾款金额快照')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('applications') as batch_op:
        batch_op.drop_column('fee_balance')
        batch_op.drop_column('fee_deposit')
        batch_op.drop_column('fee_total')
