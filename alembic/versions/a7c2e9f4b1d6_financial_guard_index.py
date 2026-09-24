"""financial_records order+teacher guard index

恢复投递的资金守卫（applications.py restore 路径）按
order_id + teacher_id 精确匹配流水，原 idx_fin_teacher 单列索引
选择性不足，流水增长后守卫查询退化。补复合索引。

Revision ID: a7c2e9f4b1d6
Revises: f2b7e3a9c5d8
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c2e9f4b1d6'
down_revision: Union[str, Sequence[str], None] = 'f2b7e3a9c5d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_fin_order_teacher', 'financial_records', ['order_id', 'teacher_id'])


def downgrade() -> None:
    op.drop_index('idx_fin_order_teacher', table_name='financial_records')
