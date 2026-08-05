"""create week3 queries and citations tables

Revision ID: 20260221_0004
Revises: 20260221_0003
Create Date: 2026-02-21 00:00:02
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260221_0004"
down_revision = "20260221_0003"
branch_labels = None
depends_on = None


def _create_rls_policy(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation_{table_name}
        ON {table_name}
        USING (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        """)


def _drop_rls_policy(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text(), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_queries_confidence_range",
        ),
        sa.CheckConstraint("top_k >= 1", name="ck_queries_top_k_positive"),
    )
    op.create_index("ix_queries_tenant_created_at", "queries", ["tenant_id", "created_at"])
    op.create_index(
        "ix_queries_tenant_user_created_at",
        "queries",
        ["tenant_id", "user_id", "created_at"],
    )

    op.create_table(
        "query_citations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id"], ["queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "query_id",
            "chunk_id",
            name="uq_query_citations_tenant_query_chunk",
        ),
        sa.CheckConstraint(
            "similarity_score >= 0.0", name="ck_query_citations_similarity_non_negative"
        ),
    )
    op.create_index("ix_query_citations_tenant_query", "query_citations", ["tenant_id", "query_id"])
    op.create_index(
        "ix_query_citations_tenant_document",
        "query_citations",
        ["tenant_id", "document_id"],
    )

    _create_rls_policy("queries")
    _create_rls_policy("query_citations")


def downgrade() -> None:
    _drop_rls_policy("query_citations")
    _drop_rls_policy("queries")

    op.drop_index("ix_query_citations_tenant_document", table_name="query_citations")
    op.drop_index("ix_query_citations_tenant_query", table_name="query_citations")
    op.drop_table("query_citations")

    op.drop_index("ix_queries_tenant_user_created_at", table_name="queries")
    op.drop_index("ix_queries_tenant_created_at", table_name="queries")
    op.drop_table("queries")
