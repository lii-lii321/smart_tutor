"""application trial_started_at / completed_at（教员投递时间线补时间）

applications 表此前六个事件时间缺"开始试课"与"成交完成"两个动作——
教员端投递时间线"试课/成交"节点无时间可显（用户 2026-10-18 实测反馈）。

存量推断回填口径（业务上成立，注释留痕）：
- trial_started_at ≈ deposit_paid_at（定金确认后中介即安排试课）
- completed_at ≈ balance_paid_at（尾款付清即成交）
新写入由端点显式赋值（start_trial_application / complete_application）。

Revision ID: j7d9c4e8f2a6
Revises: i5c8d2e6f9a4
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'j7d9c4e8f2a6'
down_revision: Union[str, Sequence[str], None] = 'i5c8d2e6f9a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("trial_started_at", sa.TIMESTAMP(), nullable=True, comment="开始试课时间（start_trial 写入）"),
    )
    op.add_column(
        "applications",
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True, comment="成交完成时间（complete 写入）"),
    )
    # 存量推断回填（方言通用写法）：
    op.execute(
        "UPDATE applications SET trial_started_at = deposit_paid_at "
        "WHERE trial_started_at IS NULL AND deposit_paid_at IS NOT NULL"
    )
    op.execute(
        "UPDATE applications SET completed_at = balance_paid_at "
        "WHERE completed_at IS NULL AND status = 'completed' AND balance_paid_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("applications", "completed_at")
    op.drop_column("applications", "trial_started_at")
