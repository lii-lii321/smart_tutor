"""widen fee columns to DECIMAL(10,2) (F15)

精算值 = 单次课酬 × 每周次数 × 频次倍率（services/calculator.py，最小综合倍率 1.5）。
base_price 的 schema 上限 le=999999.99（models/schemas.py）内合法输入即可算出
超出 DECIMAL(8,2) 上限 999999.99 的金额（如 700000×1×1.5 = 1,050,000.00），
生产 MySQL 严格模式落库必 1264 DataError（修复前 500；F14 兜底后为误导性 422）。

同根因加宽 7 列（同一精算值的存储/快照/流水三段）：
- orders.calculated_info_fee / deposit_amount / balance_amount（导入与改价落库）
- applications.fee_total / fee_deposit / fee_balance（confirm_deposit 写入的费率快照）
- financial_records.amount（定金/尾款/退款流水，金额直接来自上述精算值）
加宽至 DECIMAL(10,2) 后，schema 极值精算 999999.99×14×1.5 = 20,999,999.79
仍在上限 99,999,999.99 之内。纯加宽、不改写数据。

Revision ID: m3b9e2c6f8a4
Revises: k8f3b6d1e4c9
Create Date: 2026-10-28

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'm3b9e2c6f8a4'
down_revision: Union[str, Sequence[str], None] = 'k8f3b6d1e4c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch 形态方言通用：MySQL 直接 ALTER MODIFY（逐列保住 nullable/comment），SQLite 走表重建
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column(
            "calculated_info_fee",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=False,
            existing_comment="全额信息费",
        )
        batch_op.alter_column(
            "deposit_amount",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=True,
            existing_comment="锁定定金",
        )
        batch_op.alter_column(
            "balance_amount",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=False,
            existing_comment="需补齐尾款",
        )

    with op.batch_alter_table("applications") as batch_op:
        batch_op.alter_column(
            "fee_total",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=True,
            existing_comment="定金确认时的全额信息费快照",
        )
        batch_op.alter_column(
            "fee_deposit",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=True,
            existing_comment="定金确认时的定金金额快照",
        )
        batch_op.alter_column(
            "fee_balance",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=True,
            existing_comment="定金确认时的尾款金额快照",
        )

    with op.batch_alter_table("financial_records") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.DECIMAL(8, 2),
            type_=sa.DECIMAL(10, 2),
            existing_nullable=False,
            existing_comment="涉及金额",
        )


def downgrade() -> None:
    # 不做收缩：存量行可能已存 >999999.99 的合法金额，缩回 (8,2) 会立即触发 1264；
    # 确需回滚先手工清理超容数据再 ALTER。
    pass
