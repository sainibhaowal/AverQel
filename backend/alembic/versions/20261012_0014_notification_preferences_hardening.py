"""Add recipient time zones for notification digest scheduling."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261012_0014"
down_revision = "20261012_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_notification_preferences",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )
    op.create_index(
        "ix_notification_deliveries_recipient_due",
        "notification_deliveries",
        ["tenant_id", "recipient_user_id", "status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_recipient_due", table_name="notification_deliveries")
    op.drop_column("user_notification_preferences", "timezone")
