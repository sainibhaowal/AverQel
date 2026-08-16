"""Add durable storage cleanup jobs for admin deletion recovery.

Revision ID: 20260816_0001
Revises: 20260808_0001
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260816_0001"
down_revision = "20260808_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_cleanup_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storage_cleanup_jobs_tenant_id", "storage_cleanup_jobs", ["tenant_id"])
    op.create_index(
        "ix_storage_cleanup_jobs_owner_user_id", "storage_cleanup_jobs", ["owner_user_id"]
    )
    op.create_index("ix_storage_cleanup_jobs_status", "storage_cleanup_jobs", ["status"])
    op.create_index(
        "ix_storage_cleanup_jobs_next_attempt_at", "storage_cleanup_jobs", ["next_attempt_at"]
    )
    op.execute("ALTER TABLE storage_cleanup_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE storage_cleanup_jobs FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_storage_cleanup_jobs ON storage_cleanup_jobs
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
    """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_storage_cleanup_jobs ON storage_cleanup_jobs"
    )
    op.execute("ALTER TABLE storage_cleanup_jobs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE storage_cleanup_jobs DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_storage_cleanup_jobs_next_attempt_at", table_name="storage_cleanup_jobs")
    op.drop_index("ix_storage_cleanup_jobs_status", table_name="storage_cleanup_jobs")
    op.drop_index("ix_storage_cleanup_jobs_owner_user_id", table_name="storage_cleanup_jobs")
    op.drop_index("ix_storage_cleanup_jobs_tenant_id", table_name="storage_cleanup_jobs")
    op.drop_table("storage_cleanup_jobs")
