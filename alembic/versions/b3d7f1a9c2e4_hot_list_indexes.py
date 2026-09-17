"""hot list indexes

列表页高频查询补索引：数据量上来后无索引排序会退化为 filesort/全表扫。

Revision ID: b3d7f1a9c2e4
Revises: f8a3c1e5d7b9
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa

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
    bind = op.get_bind()
    is_mysql = bind.dialect.name == "mysql"
    fk_names: list[str] = []
    if is_mysql:
        # MySQL 1553：idx_blacklist_teacher 可能已成为 teacher_id 上 FK 的唯一支撑索引
        # （唯一约束 (tenant_id, teacher_id) 前导列是 tenant_id，撑不住 FK），直接删索引报
        # "needed in a foreign key constraint"。先摘 FK → 删索引 → 重建 FK，
        # MySQL 自动补回隐式支撑索引，与升级前状态等价。
        fks = sa.inspect(bind).get_foreign_keys("tenant_teacher_blacklist")
        fk_names = [fk["name"] for fk in fks if fk.get("name")]
        for name in fk_names:
            bind.execute(sa.text(
                f"ALTER TABLE tenant_teacher_blacklist DROP FOREIGN KEY `{name}`"
            ))
    op.drop_index('idx_blacklist_teacher', table_name='tenant_teacher_blacklist')
    op.drop_index('idx_audit_created', table_name='audit_logs')
    op.drop_index('idx_notification_tenant_created', table_name='notifications')
    op.drop_index('idx_app_teacher_status', table_name='applications')
    op.drop_index('idx_status_created', table_name='orders')
    op.drop_index('idx_tenant_status_created', table_name='orders')
    if is_mysql:
        for _name in fk_names:
            op.create_foreign_key(
                None, "tenant_teacher_blacklist", "teachers", ["teacher_id"], ["id"]
            )
