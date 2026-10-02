"""Add the bounded DeepSpace conversation retrieval index.

The index is derived data only. Existing messages, versions, runtime state, and
chat behavior remain authoritative and unchanged. Existing rows are indexed by
the resumable worker; this migration does not call providers or rewrite chat.
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import get_settings

revision = "20260929_0001"
down_revision = "20260928_0001"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSION = get_settings().embedding_dimension


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "deepspace_conversation_retrieval_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("message_versions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding_vector", Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column("embedding_provider", sa.String(120), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("embedding_version", sa.String(64), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "message_id",
            "message_version_id",
            "chunk_index",
            name="uq_deepspace_retrieval_message_version_chunk",
        ),
    )
    op.create_index(
        "ix_deepspace_retrieval_tenant_conversation",
        "deepspace_conversation_retrieval_chunks",
        ["tenant_id", "user_id", "conversation_id", "created_at"],
    )
    op.create_index(
        "ix_deepspace_retrieval_search_vector",
        "deepspace_conversation_retrieval_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_deepspace_retrieval_embedding_vector_hnsw",
        "deepspace_conversation_retrieval_chunks",
        ["embedding_vector"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_l2_ops"},
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION deepspace_retrieval_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """)
    op.execute("""
        CREATE TRIGGER trg_deepspace_retrieval_search_vector
        BEFORE INSERT OR UPDATE OF content ON deepspace_conversation_retrieval_chunks
        FOR EACH ROW EXECUTE FUNCTION deepspace_retrieval_search_vector_update();
        """)
    op.execute("ALTER TABLE deepspace_conversation_retrieval_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE deepspace_conversation_retrieval_chunks FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY deepspace_retrieval_tenant_isolation
        ON deepspace_conversation_retrieval_chunks
        USING (
          current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        WITH CHECK (
          current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_deepspace_retrieval_search_vector ON deepspace_conversation_retrieval_chunks"
    )
    op.execute("DROP FUNCTION IF EXISTS deepspace_retrieval_search_vector_update()")
    op.drop_index(
        "ix_deepspace_retrieval_embedding_vector_hnsw",
        table_name="deepspace_conversation_retrieval_chunks",
    )
    op.drop_index(
        "ix_deepspace_retrieval_search_vector", table_name="deepspace_conversation_retrieval_chunks"
    )
    op.drop_index(
        "ix_deepspace_retrieval_tenant_conversation",
        table_name="deepspace_conversation_retrieval_chunks",
    )
    op.drop_table("deepspace_conversation_retrieval_chunks")
