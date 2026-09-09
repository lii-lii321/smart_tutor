"""unique phone on teachers

Revision ID: d9a6c1f4e2b8
Revises: c8f5b2e3a4d6
Create Date: 2026-09-06

手机号是教员登录凭证，必须唯一：历史上无约束时并发/重复注册会产生
同号多账号，登录 limit(1) 取到哪条不确定，等于账号被随机遮蔽。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd9a6c1f4e2b8'
down_revision: Union[str, Sequence[str], None] = 'c8f5b2e3a4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 若历史数据存在重复手机号，唯一索引会创建失败；
    # 需先人工合并/改号（测试库可用脚本改号），生产执行前先跑检查：
    #   SELECT phone, COUNT(*) FROM teachers GROUP BY phone HAVING COUNT(*) > 1;
    # SQLite 不支持 ALTER 加约束，走 batch 重建表（MySQL 下 batch 等价于直接 ALTER）
    with op.batch_alter_table("teachers") as batch_op:
        batch_op.create_unique_constraint("uk_teachers_phone", ["phone"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("teachers") as batch_op:
        batch_op.drop_constraint("uk_teachers_phone", type_="unique")
