"""Allow account erasure to anonymize queued storage cleanup ownership.

Revision ID: 20261018_0001
Revises: 20261017_0002
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261018_0001"
down_revision = "20261017_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "storage_cleanup_jobs",
        "owner_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # The prior owner is intentionally not recoverable after erasure. Use a non-account sentinel
    # only when downgrading this schema so the original NOT NULL constraint can be restored.
    op.execute(
        "UPDATE storage_cleanup_jobs "
        "SET owner_user_id = '00000000-0000-0000-0000-000000000000' "
        "WHERE owner_user_id IS NULL"
    )
    op.alter_column(
        "storage_cleanup_jobs",
        "owner_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
