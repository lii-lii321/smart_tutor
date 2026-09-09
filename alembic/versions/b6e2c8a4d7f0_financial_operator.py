"""operator_role on financial_records

Revision ID: b6e2c8a4d7f0
Revises: e7d3a9c1b5f4
Create Date: 2026-09-06

财务流水记录登记人角色，满足线下收款模式的最小审计需求。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6e2c8a4d7f0'
down_revision: Union[str, Sequence[str], None] = 'e7d3a9c1b5f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'financial_records',
        sa.Column('operator_role', sa.String(length=20), nullable=True,
                  comment='登记人角色：tenant_admin/super_admin/teacher'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('financial_records', 'operator_role')
