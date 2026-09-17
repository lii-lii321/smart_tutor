"""notifications deleted_at

用户主动删除通知的软删标记列：行必须保留作为调度器临期提醒的周期去重锚点。

Revision ID: c5e9f2b7a8d1
Revises: b3d7f1a9c2e4
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e9f2b7a8d1'
down_revision: Union[str, Sequence[str], None] = 'b3d7f1a9c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'notifications',
        sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True, comment='软删标记：用户删除时刻，NULL=未删除'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notifications', 'deleted_at')
