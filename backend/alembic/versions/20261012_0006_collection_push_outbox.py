"""Add a durable collection notification push outbox."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0006"
down_revision = "20261012_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_push_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["collection_notifications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", name="uq_collection_push_delivery_notification"),
    )
    op.create_index(
        "ix_collection_push_deliveries_recipient_user_id",
        "collection_push_deliveries",
        ["recipient_user_id"],
    )
    op.create_index(
        "ix_collection_push_deliveries_status", "collection_push_deliveries", ["status"]
    )
    op.create_index(
        "ix_collection_push_deliveries_next_attempt_at",
        "collection_push_deliveries",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_collection_push_deliveries_status_next",
        "collection_push_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_push_deliveries_status_next", table_name="collection_push_deliveries"
    )
    op.drop_index(
        "ix_collection_push_deliveries_next_attempt_at", table_name="collection_push_deliveries"
    )
    op.drop_index("ix_collection_push_deliveries_status", table_name="collection_push_deliveries")
    op.drop_index(
        "ix_collection_push_deliveries_recipient_user_id", table_name="collection_push_deliveries"
    )
    op.drop_table("collection_push_deliveries")
