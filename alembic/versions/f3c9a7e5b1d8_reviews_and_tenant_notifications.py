"""order_reviews table, notifications for tenants

Revision ID: f3c9a7e5b1d8
Revises: e1b8d5c7f4a2
Create Date: 2026-09-06

- order_reviews：中介对成交教员的评价（一单一评），进教员信用与推荐分
- notifications：支持租户作为接收人（teacher_id 改为可空，新增 tenant_id）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c9a7e5b1d8'
down_revision: Union[str, Sequence[str], None] = 'e1b8d5c7f4a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'order_reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False, comment='订单（一单一评）'),
        sa.Column('application_id', sa.Integer(), nullable=False, comment='成交的投递'),
        sa.Column('tenant_id', sa.Integer(), nullable=False, comment='评价方租户'),
        sa.Column('teacher_id', sa.Integer(), nullable=False, comment='被评教员'),
        sa.Column('rating', sa.Integer(), nullable=False, comment='评分 1-5 星'),
        sa.Column('comment', sa.String(length=255), nullable=True, comment='评语'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id'),
    )

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.alter_column(
            'teacher_id', existing_type=sa.Integer(), nullable=True,
            comment='C 端接收教员',
        )
        batch_op.add_column(
            sa.Column('tenant_id', sa.Integer(), nullable=True,
                      comment='B 端接收租户（与 teacher_id 二选一）')
        )
    op.create_index('idx_notification_tenant', 'notifications', ['tenant_id', 'read_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_notification_tenant', table_name='notifications')
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_column('tenant_id')
        batch_op.alter_column('teacher_id', existing_type=sa.Integer(), nullable=False)
    op.drop_table('order_reviews')
