"""Add tenant-scoped Grounded Query table indexes."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0015"
down_revision = "20261012_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query_dataset_indexes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column(
            "stage", sa.String(length=32), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column(
            "columns",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("derivative_bucket", sa.String(length=255), nullable=True),
        sa.Column("derivative_object_key", sa.String(length=1024), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_query_dataset_progress_range"
        ),
        sa.CheckConstraint(
            "row_count IS NULL OR row_count >= 0", name="ck_query_dataset_rows_nonnegative"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "document_id", name="uq_query_dataset_document"),
    )
    op.create_index("ix_query_dataset_indexes_tenant_id", "query_dataset_indexes", ["tenant_id"])
    op.create_index(
        "ix_query_dataset_indexes_document_id", "query_dataset_indexes", ["document_id"]
    )
    op.create_index("ix_query_dataset_indexes_status", "query_dataset_indexes", ["status"])
    op.execute("ALTER TABLE query_dataset_indexes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE query_dataset_indexes FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation_query_dataset_indexes ON query_dataset_indexes
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_query_dataset_indexes ON query_dataset_indexes"
    )
    op.drop_index("ix_query_dataset_indexes_status", table_name="query_dataset_indexes")
    op.drop_index("ix_query_dataset_indexes_document_id", table_name="query_dataset_indexes")
    op.drop_index("ix_query_dataset_indexes_tenant_id", table_name="query_dataset_indexes")
    op.drop_table("query_dataset_indexes")
