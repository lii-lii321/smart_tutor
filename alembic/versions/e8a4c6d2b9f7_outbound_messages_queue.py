"""outbound_messages queue for notification channels

触达通道出站队列：站内信之外的推送排队由 scheduler 异步投递。
队列表与站内信同事务写入，业务回滚不发假通知；通道故障留痕可重试。

Revision ID: e8a4c6d2b9f7
Revises: c5e9f2b7a8d1
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8a4c6d2b9f7'
down_revision: Union[str, Sequence[str], None] = 'c5e9f2b7a8d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbound_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event', sa.String(length=50), nullable=False,
                  comment='事件标识：teacher.notify/tenant.application_received 等'),
        sa.Column('title', sa.String(length=50), nullable=False,
                  comment='标题（与站内信同口径截断）'),
        sa.Column('content', sa.String(length=255), comment='正文'),
        sa.Column('teacher_id', sa.Integer(), nullable=True,
                  comment='目标教员（点对点通道如短信按此取手机号）'),
        sa.Column('tenant_id', sa.Integer(), nullable=True, comment='目标租户'),
        sa.Column('status', sa.String(length=10), nullable=False,
                  comment='pending/sent/failed/dead（重试耗尽）'),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(length=255), comment='最近一次投递失败原因（截断）'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=True, comment='成功投递时间'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_outbound_status', 'outbound_messages', ['status', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_outbound_status', table_name='outbound_messages')
    op.drop_table('outbound_messages')
