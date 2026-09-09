"""hot query composite indexes

Revision ID: d5b9e7c3a1f2
Revises: b6e2c8a4d7f0
Create Date: 2026-09-09

高频查询补复合索引：
- orders(status, expired_at)：scheduler 每 5 分钟的过期归档/提醒扫描与教员端按到期排序；
- applications(order_id, status)：资金守卫（_ensure_reopenable）与订单投递列表；
- applications(tenant_id, status)：B 端待审投递统计；
- notifications(order_id)：过期提醒按单查重。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5b9e7c3a1f2'
down_revision: Union[str, Sequence[str], None] = 'b6e2c8a4d7f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('idx_status_expired', 'orders', ['status', 'expired_at'])
    op.create_index('idx_app_order_status', 'applications', ['order_id', 'status'])
    op.create_index('idx_app_tenant_status', 'applications', ['tenant_id', 'status'])
    op.create_index('idx_notification_order', 'notifications', ['order_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_notification_order', table_name='notifications')
    op.drop_index('idx_app_tenant_status', table_name='applications')
    op.drop_index('idx_app_order_status', table_name='applications')
    op.drop_index('idx_status_expired', table_name='orders')
