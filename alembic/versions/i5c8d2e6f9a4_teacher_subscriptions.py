"""teacher subscriptions（教员找单订阅偏好）

一教员一行的订阅偏好表：新订单入库后按偏好匹配并发站内信（教员订阅推送）。
多选字段存规范名逗号分隔，空=不限（见 models/domain.TeacherSubscription）。

Revision ID: i5c8d2e6f9a4
Revises: h4c9e2f7a1d5
Create Date: 2026-10-17

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i5c8d2e6f9a4"
down_revision: Union[str, Sequence[str], None] = "h4c9e2f7a1d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teacher_subscriptions",
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("subjects", sa.String(length=120), nullable=True),
        sa.Column("grades", sa.String(length=60), nullable=True),
        sa.Column("min_base_price", sa.DECIMAL(8, 2), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"]),
        sa.PrimaryKeyConstraint("teacher_id"),
    )


def downgrade() -> None:
    op.drop_table("teacher_subscriptions")
