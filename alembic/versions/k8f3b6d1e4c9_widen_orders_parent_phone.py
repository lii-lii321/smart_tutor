"""widen orders.parent_phone for PII ciphertext (F14)

orders.parent_phone 建库为 VARCHAR(20)（a9a54481a950），且此后无加宽迁移
（b3e7f1a9c4d8 注明「同列，无 schema 变更」）。ADR-0005 落地后该列存的是
AES-256-GCM 密文 "v1:" + base64(12B nonce + ciphertext + 16B tag)：11 位手机号
即 55 字符——生产配置 PII_ENC_KEY 后 B 端录单只要带家长电话必触发 MySQL
1406 DataError → 500。加宽到 VARCHAR(80)（20 位电话密文 67 字符仍可容纳）。

纯加宽、不改写任何数据，b3e7f1a9c4d8 的存量回填无需重跑。

Revision ID: k8f3b6d1e4c9
Revises: j7d9c4e8f2a6
Create Date: 2026-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'k8f3b6d1e4c9'
down_revision: Union[str, Sequence[str], None] = 'j7d9c4e8f2a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch 形态方言通用：MySQL 直接 ALTER MODIFY（保住 nullable/comment），SQLite 开发库走表重建
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column(
            "parent_phone",
            existing_type=sa.String(length=20),
            type_=sa.String(length=80),
            existing_nullable=True,
            existing_comment="家长联系电话（尾款解锁）",
        )


def downgrade() -> None:
    # 不做收缩：存量行已是 ~55 字符密文，缩回 20 会立即触发 1406；
    # 确需回滚先手工清理密文数据再 ALTER。
    pass
