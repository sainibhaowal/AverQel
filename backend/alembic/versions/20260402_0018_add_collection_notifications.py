from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260402_0018"
down_revision = "20260402_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("collection_name", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_notifications_recipient_user_id",
        "collection_notifications",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_collection_notifications_actor_user_id",
        "collection_notifications",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_collection_notifications_collection_id",
        "collection_notifications",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        "ix_collection_notifications_event_type",
        "collection_notifications",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_notifications_event_type", table_name="collection_notifications"
    )
    op.drop_index(
        "ix_collection_notifications_collection_id",
        table_name="collection_notifications",
    )
    op.drop_index(
        "ix_collection_notifications_actor_user_id",
        table_name="collection_notifications",
    )
    op.drop_index(
        "ix_collection_notifications_recipient_user_id",
        table_name="collection_notifications",
    )
    op.drop_table("collection_notifications")
