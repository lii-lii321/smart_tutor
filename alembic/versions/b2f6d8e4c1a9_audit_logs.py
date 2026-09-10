"""audit_logs table

Revision ID: b2f6d8e4c1a9
Revises: d5b9e7c3a1f2
Create Date: 2026-09-10

资金操作审计日志（PLAN P2-6）：与 financial_records.operator_role 互补——
流水记录"钱怎么动"，审计记录"谁、何时、从哪个 IP 动的"。
写路径：confirm_deposit / confirm_balance / trial_failed / forfeit / cancel。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2f6d8e4c1a9'
down_revision: Union[str, Sequence[str], None] = 'd5b9e7c3a1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True, comment='数据归属租户（教员取消时为其投递目标租户）'),
        sa.Column('actor_role', sa.String(length=20), nullable=False, comment='操作人角色：tenant_admin/super_admin/teacher'),
        sa.Column('actor_id', sa.Integer(), nullable=False, comment='操作人 ID（随角色：租户 ID / 教员 ID / 0）'),
        sa.Column('action', sa.String(length=40), nullable=False, comment='动作：confirm_deposit/confirm_balance/trial_failed/forfeit/cancel'),
        sa.Column('object_type', sa.String(length=20), nullable=False, comment='对象类型：application'),
        sa.Column('object_id', sa.Integer(), nullable=False, comment='对象 ID（投递 ID）'),
        sa.Column('ip', sa.String(length=45), nullable=True, comment='客户端 IP（IPv6 最长 45 字符）'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_tenant_created', 'audit_logs', ['tenant_id', 'created_at'])
    op.create_index('idx_audit_object', 'audit_logs', ['object_type', 'object_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # 两个索引均非外键列依赖（本表无外键），可独立删除
    op.drop_index('idx_audit_object', table_name='audit_logs')
    op.drop_index('idx_audit_tenant_created', table_name='audit_logs')
    op.drop_table('audit_logs')
