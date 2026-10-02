"""Harden collection chat storage, receipts, and idempotency."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0001"
down_revision = "20261011_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collection_chat_messages",
        sa.Column("client_message_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "collection_chat_messages",
        sa.Column("media_object_key", sa.String(length=1024), nullable=True),
    )
    op.create_index(
        "ix_collection_chat_messages_client_message_id",
        "collection_chat_messages",
        ["client_message_id"],
    )
    op.create_unique_constraint(
        "uq_collection_chat_client_message",
        "collection_chat_messages",
        ["collection_id", "user_id", "client_message_id"],
    )
    op.create_table(
        "collection_chat_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["collection_chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["document_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_collection_chat_delivery_recipient"),
    )
    op.create_index(
        "ix_collection_chat_deliveries_message_id",
        "collection_chat_deliveries",
        ["message_id"],
    )
    op.create_index(
        "ix_collection_chat_deliveries_collection_id",
        "collection_chat_deliveries",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_chat_deliveries_user_id",
        "collection_chat_deliveries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_chat_deliveries_user_id", table_name="collection_chat_deliveries")
    op.drop_index(
        "ix_collection_chat_deliveries_collection_id", table_name="collection_chat_deliveries"
    )
    op.drop_index(
        "ix_collection_chat_deliveries_message_id", table_name="collection_chat_deliveries"
    )
    op.drop_table("collection_chat_deliveries")
    op.drop_index(
        "ix_collection_chat_messages_client_message_id", table_name="collection_chat_messages"
    )
    op.drop_constraint(
        "uq_collection_chat_client_message",
        "collection_chat_messages",
        type_="unique",
    )
    op.drop_column("collection_chat_messages", "media_object_key")
    op.drop_column("collection_chat_messages", "client_message_id")
