"""Persist document-level malware scan receipts for the document pipeline."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261001_0001"
down_revision = "20260930_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("security_scan_result", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("security_scan_reason", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("security_scanned_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("documents", "security_scanned_at")
    op.drop_column("documents", "security_scan_reason")
    op.drop_column("documents", "security_scan_result")
