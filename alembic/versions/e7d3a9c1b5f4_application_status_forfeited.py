"""application status + forfeited

Revision ID: e7d3a9c1b5f4
Revises: c2a7e9b4d1f3
Create Date: 2026-09-08

投递状态机补充终态 `forfeited`（试课失败/教员违约，定金已没收）：
此前没收处置与普通落选共用 `rejected`，台账有没收流水而状态显示"已拒绝"，
中介与教员都无法从状态上看出资金已按约定没收。
MySQL 的 ENUM 列需要 alter_column 扩展枚举值；SQLite（本地开发）为字符串存储无需变更。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = 'e7d3a9c1b5f4'
down_revision: Union[str, Sequence[str], None] = 'c2a7e9b4d1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_STATUS = mysql.ENUM(
    'pending', 'shortlisted', 'trial_in_progress', 'deposit_paid',
    'balance_paid', 'completed', 'rejected', 'refunded',
    name='applicationstatus',
)
_NEW_STATUS = mysql.ENUM(
    'pending', 'shortlisted', 'trial_in_progress', 'deposit_paid',
    'balance_paid', 'completed', 'rejected', 'refunded', 'forfeited',
    name='applicationstatus',
)


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 为字符串存储，无需扩展枚举
        return
    op.alter_column(
        'applications', 'status',
        existing_type=_OLD_STATUS,
        type_=_NEW_STATUS,
        existing_nullable=True,
        existing_comment='投递状态',
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        return
    # 回滚前必须先把 forfeited 行改回 rejected，否则 ENUM 收缩会因非法值失败
    op.execute("UPDATE applications SET status = 'rejected' WHERE status = 'forfeited'")
    op.alter_column(
        'applications', 'status',
        existing_type=_NEW_STATUS,
        type_=_OLD_STATUS,
        existing_nullable=True,
        existing_comment='投递状态',
    )
