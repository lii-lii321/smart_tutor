"""tenant_teacher_blacklist table

Revision ID: a4d8f2e6c9b1
Revises: f3c9a7e5b1d8
Create Date: 2026-09-06

中介级教员黑名单：中介可拉黑不负责任的教员，仅限制本租户的投递与推荐；
全局封禁仍是平台老板的权限。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4d8f2e6c9b1'
down_revision: Union[str, Sequence[str], None] = 'f3c9a7e5b1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tenant_teacher_blacklist',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False, comment='拉黑方租户'),
        sa.Column('teacher_id', sa.Integer(), nullable=False, comment='被拉黑教员'),
        sa.Column('reason', sa.String(length=255), nullable=True, comment='拉黑原因'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'teacher_id', name='uk_tenant_teacher_black'),
    )
    op.create_index('idx_blacklist_tenant', 'tenant_teacher_blacklist', ['tenant_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_blacklist_tenant', table_name='tenant_teacher_blacklist')
    op.drop_table('tenant_teacher_blacklist')
