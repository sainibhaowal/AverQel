"""Require a different administrator to approve workspace deletion."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261017_0002"
down_revision = "20261017_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_deletions",
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "data_deletions",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_data_deletions_approved_by_user_id",
        "data_deletions",
        ["approved_by_user_id"],
        unique=False,
    )
    # Pending requests from the one-person flow must be re-approved before
    # workers are allowed to perform a destructive purge.
    op.execute("UPDATE data_deletions SET status = 'awaiting_approval' WHERE status = 'queued'")


def downgrade() -> None:
    op.drop_index("ix_data_deletions_approved_by_user_id", table_name="data_deletions")
    op.drop_column("data_deletions", "approved_at")
    op.drop_column("data_deletions", "approved_by_user_id")
