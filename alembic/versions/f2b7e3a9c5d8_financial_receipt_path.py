"""financial receipt_path column for payment proof

收款凭证（转账截图）落 financial_records.receipt_path：
半线上化的对账增强——凭证随流水保留（流水按对账红线已不可删）。

Revision ID: f2b7e3a9c5d8
Revises: e8a4c6d2b9f7
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b7e3a9c5d8'
down_revision: Union[str, Sequence[str], None] = 'e8a4c6d2b9f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'financial_records',
        sa.Column('receipt_path', sa.String(length=255), nullable=True,
                  comment='收款凭证文件相对路径（空=未上传）'),
    )


def downgrade() -> None:
    op.drop_column('financial_records', 'receipt_path')
