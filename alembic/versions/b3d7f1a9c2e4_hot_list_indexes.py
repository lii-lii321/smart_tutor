"""hot list indexes

列表页高频查询补索引：数据量上来后无索引排序会退化为 filesort/全表扫。

Revision ID: b3d7f1a9c2e4
Revises: f8a3c1e5d7b9
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3d7f1a9c2e4'
down_revision: Union[str, Sequence[str], None] = 'f8a3c1e5d7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # orders：B 端(tenant+status)与 C 端(recruiting)列表按 created_at 倒序分页
    op.create_index('idx_tenant_status_created', 'orders', ['tenant_id', 'status', 'created_at'], unique=False)
    op.create_index('idx_status_created', 'orders', ['status', 'created_at'], unique=False)
    # applications：教员"我的投递"按 teacher_id + 终态过滤
    op.create_index('idx_app_teacher_status', 'applications', ['teacher_id', 'status'], unique=False)
    # notifications：B 端通知列表按 created_at 倒序
    op.create_index('idx_notification_tenant_created', 'notifications', ['tenant_id', 'created_at'], unique=False)
    # audit_logs：超管不带租户过滤的 created_at 倒序
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'], unique=False)
    # tenant_teacher_blacklist：按教员查黑名单（唯一约束第二列走不了索引）
    op.create_index('idx_blacklist_teacher', 'tenant_teacher_blacklist', ['teacher_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_blacklist_teacher', table_name='tenant_teacher_blacklist')
    op.drop_index('idx_audit_created', table_name='audit_logs')
    op.drop_index('idx_notification_tenant_created', table_name='notifications')
    op.drop_index('idx_app_teacher_status', table_name='applications')
    op.drop_index('idx_status_created', table_name='orders')
    op.drop_index('idx_tenant_status_created', table_name='orders')
