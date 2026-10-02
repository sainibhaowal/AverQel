"""Add resumable retention-run metadata."""

import sqlalchemy as sa

from alembic import op

revision = "20260927_0001"
down_revision = "20260926_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "storage_retention_runs",
        sa.Column("operation", sa.String(24), nullable=False, server_default=sa.text("'preview'")),
    )
    op.add_column(
        "storage_retention_runs", sa.Column("checkpoint_cursor", sa.String(255), nullable=True)
    )
    op.add_column(
        "storage_retention_runs",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("storage_retention_runs", "lease_until")
    op.drop_column("storage_retention_runs", "checkpoint_cursor")
    op.drop_column("storage_retention_runs", "operation")
