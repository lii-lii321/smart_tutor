"""encrypt order parent PII at rest (ADR-0005)

存量回填：orders.exact_address / parent_phone 明文行就地加密为 "v1:" 前缀密文（同列，
无 schema 变更）。PII_ENC_KEY 未配置（本地开发直通模式）时跳过——读端对明文遗留行
永久兼容，回填可以在任意时间点带密钥重跑（已加密行按前缀识别、天然幂等）。

Revision ID: b3e7f1a9c4d8
Revises: a7c2e9f4b1d6
Create Date: 2026-10-03

"""
import logging
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3e7f1a9c4d8'
down_revision: Union[str, Sequence[str], None] = 'a7c2e9f4b1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_CIPHER_PREFIX = "v1:"


def upgrade() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from config import settings  # noqa: E402
    from services.pii_crypto import encrypt_pii  # noqa: E402

    if not (settings.PII_ENC_KEY or "").strip():
        logger.warning("PII_ENC_KEY 未配置：跳过家长 PII 回填（开发直通模式；生产由启动校验强制配钥）")
        return

    bind = op.get_bind()
    orders = sa.table(
        "orders",
        sa.column("id", sa.Integer),
        sa.column("exact_address", sa.String),
        sa.column("parent_phone", sa.String),
    )
    rows = bind.execute(
        sa.select(orders.c.id, orders.c.exact_address, orders.c.parent_phone)
    ).fetchall()

    updated = 0
    for order_id, exact_address, parent_phone in rows:
        new_exact = (
            encrypt_pii(exact_address)
            if exact_address and not exact_address.startswith(_CIPHER_PREFIX)
            else exact_address
        )
        new_phone = (
            encrypt_pii(parent_phone)
            if parent_phone and not parent_phone.startswith(_CIPHER_PREFIX)
            else parent_phone
        )
        if new_exact == exact_address and new_phone == parent_phone:
            continue
        # Core 表达式 → 全参数化执行
        bind.execute(
            sa.update(orders)
            .where(orders.c.id == order_id)
            .values(exact_address=new_exact, parent_phone=new_phone)
        )
        updated += 1
    logger.info("家长 PII 回填完成：加密 %s 行（其余为空值或已是密文）", updated)


def downgrade() -> None:
    # 不可逆：解密需要密钥且属于安全倒退（明文落库），不做降级实现。
    # 读端本就兼容明文遗留行，确需回滚时手工解密更新即可。
    pass
