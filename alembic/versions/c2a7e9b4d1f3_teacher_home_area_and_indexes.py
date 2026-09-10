"""teacher home_area + hot query indexes

Revision ID: c2a7e9b4d1f3
Revises: a4d8f2e6c9b1
Create Date: 2026-09-07

教员资料可编辑批次：
- teachers.home_area：常驻地描述，供个人中心展示与地理编码换算坐标；
- 财务/评价表补高频查询索引（列表筛选、教员信用聚合、教员结算单）。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2a7e9b4d1f3'
down_revision: Union[str, Sequence[str], None] = 'a4d8f2e6c9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'teachers',
        sa.Column('home_area', sa.String(length=100), nullable=True, comment='常驻地描述（如：成都·武侯区），用于展示与地理编码'),
    )
    op.create_index('idx_fin_tenant_created', 'financial_records', ['tenant_id', 'created_at'])
    op.create_index('idx_fin_teacher', 'financial_records', ['teacher_id'])
    op.create_index('idx_order_review_teacher', 'order_reviews', ['teacher_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # 三个索引都建在外键列上（teacher_id/tenant_id）：升级时它们接管了外键的索引依赖，
    # 降级删除前必须先补回单列索引，否则 MySQL 报 1553 "needed in a foreign key constraint"
    op.create_index('ix_order_review_teacher', 'order_reviews', ['teacher_id'])
    op.drop_index('idx_order_review_teacher', table_name='order_reviews')
    op.create_index('ix_fin_teacher', 'financial_records', ['teacher_id'])
    op.drop_index('idx_fin_teacher', table_name='financial_records')
    op.create_index('ix_fin_tenant', 'financial_records', ['tenant_id'])
    op.drop_index('idx_fin_tenant_created', table_name='financial_records')
    op.drop_column('teachers', 'home_area')
