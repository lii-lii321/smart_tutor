"""tenant city（多城市地理编码锚点）

租户补 city 字段：录单时作为高德地理编码的 city 参数，无城市前缀的地址
（"成华区XX小区"）不再可能被解析到外地同名地名。可空列，存量租户由
运维/种子按需补值；录单时 city 为空的租户不启用城市锚定（行为同旧版）。

Revision ID: h4c9e2f7a1d5
Revises: f6b8d4a2c9e3
Create Date: 2026-10-17

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h4c9e2f7a1d5"
down_revision: Union[str, Sequence[str], None] = "f6b8d4a2c9e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "city",
            sa.String(length=20),
            nullable=True,
            comment="所在城市（如：成都）：录单地理编码的城市锚点",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "city")
