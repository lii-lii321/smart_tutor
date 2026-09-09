"""token_valid_after on teachers and tenants

Revision ID: e1b8d5c7f4a2
Revises: d9a6c1f4e2b8
Create Date: 2026-09-06

改密/重置密码后使已签发的 JWT 立即失效：
get_current_user 比对 token 签发时间（iat）与该时间戳。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1b8d5c7f4a2'
down_revision: Union[str, Sequence[str], None] = 'd9a6c1f4e2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('teachers') as batch_op:
        batch_op.add_column(
            sa.Column('token_valid_after', sa.TIMESTAMP(), nullable=True,
                      comment='早于该时间签发的 token 一律失效')
        )
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.add_column(
            sa.Column('token_valid_after', sa.TIMESTAMP(), nullable=True,
                      comment='早于该时间签发的 token 一律失效')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.drop_column('token_valid_after')
    with op.batch_alter_table('teachers') as batch_op:
        batch_op.drop_column('token_valid_after')
