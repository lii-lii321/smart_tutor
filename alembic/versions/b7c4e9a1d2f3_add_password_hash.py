"""add password_hash for teachers and tenants

Revision ID: b7c4e9a1d2f3
Revises: a9a54481a950
Create Date: 2026-09-06

教员手机号登录与中介后台登录均需要密码（bcrypt 哈希）。
历史账号未设置密码时：教员仍可用微信登录，中介需联系平台老板重置密码。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c4e9a1d2f3'
down_revision: Union[str, Sequence[str], None] = 'a9a54481a950'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('teachers') as batch_op:
        batch_op.add_column(
            sa.Column('password_hash', sa.String(length=100), nullable=True,
                      comment='登录密码哈希（bcrypt），未设置时仅可用微信登录')
        )
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.add_column(
            sa.Column('password_hash', sa.String(length=100), nullable=True,
                      comment='后台登录密码哈希（bcrypt）')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tenants') as batch_op:
        batch_op.drop_column('password_hash')
    with op.batch_alter_table('teachers') as batch_op:
        batch_op.drop_column('password_hash')
