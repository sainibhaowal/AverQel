"""create week2 document ingestion tables

Revision ID: 20260221_0003
Revises: 20260221_0002
Create Date: 2026-02-21 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260221_0003"
down_revision = "20260221_0002"
branch_labels = None
depends_on = None

EMBEDDING_DIMENSION = 8


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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_bucket", sa.String(length=128), nullable=False),
        sa.Column("storage_object_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id",
            "storage_bucket",
            "storage_object_key",
            name="uq_documents_tenant_storage_object",
        ),
    )
    op.create_index("ix_documents_tenant_created_at", "documents", ["tenant_id", "created_at"])
    op.create_index("ix_documents_tenant_status", "documents", ["tenant_id", "status"])

    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_ingestion_jobs_tenant_created_at",
        "ingestion_jobs",
        ["tenant_id", "created_at"],
    )
    op.create_index("ix_ingestion_jobs_tenant_status", "ingestion_jobs", ["tenant_id", "status"])

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "chunk_index",
            name="uq_document_chunks_tenant_document_index",
        ),
    )
    op.create_index(
        "ix_document_chunks_tenant_created_at",
        "document_chunks",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "chunk_id", name="uq_chunk_embeddings_tenant_chunk"),
    )
    op.create_index(
        "ix_chunk_embeddings_tenant_created_at",
        "chunk_embeddings",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_chunk_embeddings_embedding_hnsw",
        "chunk_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_l2_ops"},
    )

    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_idempotency_tenant_key"),
    )
    op.create_index(
        "ix_idempotency_keys_tenant_created_at",
        "idempotency_keys",
        ["tenant_id", "created_at"],
    )

    for table_name in (
        "documents",
        "ingestion_jobs",
        "document_chunks",
        "chunk_embeddings",
        "idempotency_keys",
    ):
        _create_rls_policy(table_name)


def downgrade() -> None:
    for table_name in (
        "idempotency_keys",
        "chunk_embeddings",
        "document_chunks",
        "ingestion_jobs",
        "documents",
    ):
        _drop_rls_policy(table_name)

    op.drop_index("ix_idempotency_keys_tenant_created_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("ix_chunk_embeddings_embedding_hnsw", table_name="chunk_embeddings")
    op.drop_index("ix_chunk_embeddings_tenant_created_at", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")

    op.drop_index("ix_document_chunks_tenant_created_at", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_ingestion_jobs_tenant_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_tenant_created_at", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_index("ix_documents_tenant_status", table_name="documents")
    op.drop_index("ix_documents_tenant_created_at", table_name="documents")
    op.drop_table("documents")
