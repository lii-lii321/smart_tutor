"""notifications table and teachers.is_banned

Revision ID: c8f5b2e3a4d6
Revises: b7c4e9a1d2f3
Create Date: 2026-09-06

- notifications：教员站内通知（投递被拒/候选/定金/试课/成交/处置结果）
- teachers.is_banned：平台封禁标记，封禁后不可投递与被推荐
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f5b2e3a4d6'
down_revision: Union[str, Sequence[str], None] = 'b7c4e9a1d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False, comment='接收教员'),
        sa.Column('title', sa.String(length=50), nullable=False, comment='通知标题'),
        sa.Column('content', sa.String(length=255), nullable=True, comment='通知正文'),
        sa.Column('application_id', sa.Integer(), nullable=True, comment='关联投递，可空'),
        sa.Column('order_id', sa.Integer(), nullable=True, comment='关联订单，可空'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('read_at', sa.TIMESTAMP(), nullable=True, comment='已读时间'),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_notification_teacher', 'notifications', ['teacher_id', 'read_at'])

    with op.batch_alter_table('teachers') as batch_op:
        batch_op.add_column(
            sa.Column('is_banned', sa.Boolean(), nullable=False, server_default=sa.text('0'),
                      comment='是否被平台封禁投递')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('teachers') as batch_op:
        batch_op.drop_column('is_banned')
    op.drop_index('idx_notification_teacher', table_name='notifications')
    op.drop_table('notifications')
