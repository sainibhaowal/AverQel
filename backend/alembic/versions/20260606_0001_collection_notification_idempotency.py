"""collection_notification_idempotency

Revision ID: 20260606_0001
Revises: 20260605_0002
Create Date: 2026-06-06 01:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260606_0001"
down_revision = "20260605_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collection_notifications",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_collection_notifications_idempotency_key",
        "collection_notifications",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_notifications_idempotency_key",
        table_name="collection_notifications",
    )
    op.drop_column("collection_notifications", "idempotency_key")
