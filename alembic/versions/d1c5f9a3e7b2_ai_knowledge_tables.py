"""ai knowledge base tables (阶段 1b)

创建 knowledge_documents / knowledge_chunks / ai_query_logs 三张表：
知识库文档与切片（向量 float32 BLOB 内嵌）+ AI 调用日志。纯新增表、
无存量数据回填；DEV_MODE 本地由 create_all 建表并自动对齐 alembic head。

Revision ID: d1c5f9a3e7b2
Revises: b3e7f1a9c4d8
Create Date: 2026-10-12

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1c5f9a3e7b2"
down_revision: Union[str, Sequence[str], None] = "b3e7f1a9c4d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=10), nullable=False, server_default="paste"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_reason", sa.String(length=255), nullable=True),
        sa.Column("created_by_role", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_kb_doc_tenant", "knowledge_documents", ["tenant_id", "deleted_at"])
    op.create_index("idx_kb_doc_status", "knowledge_documents", ["status"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True
        ),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_kb_chunk_doc", "knowledge_chunks", ["document_id"])
    op.create_index("idx_kb_chunk_tenant", "knowledge_chunks", ["tenant_id"])

    op.create_table(
        "ai_query_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(length=20), nullable=False),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("answer_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_document_ids", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_log_tenant_created", "ai_query_logs", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_ai_log_tenant_created", table_name="ai_query_logs")
    op.drop_table("ai_query_logs")
    op.drop_index("idx_kb_chunk_tenant", table_name="knowledge_chunks")
    op.drop_index("idx_kb_chunk_doc", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("idx_kb_doc_status", table_name="knowledge_documents")
    op.drop_index("idx_kb_doc_tenant", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
