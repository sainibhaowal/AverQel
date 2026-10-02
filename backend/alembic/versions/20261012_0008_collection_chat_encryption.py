"""Sealed collection chat: encryption flag, envelope columns, epoch keys."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0008"
down_revision = "20261012_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_collections",
        sa.Column("chat_encryption_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "collection_chat_messages",
        sa.Column("message_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "collection_chat_messages",
        sa.Column("is_encrypted", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "collection_chat_messages",
        sa.Column("crypto_epoch", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "collection_chat_messages",
        sa.Column("crypto_idx", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        "ix_collection_chat_messages_message_hash",
        "collection_chat_messages",
        ["message_hash"],
    )
    # Partial uniqueness: legacy plaintext rows share (epoch 0, idx 0) and
    # must not collide; only sealed rows carry meaningful (epoch, idx).
    op.create_index(
        "uq_collection_chat_epoch_idx",
        "collection_chat_messages",
        ["collection_id", "crypto_epoch", "crypto_idx"],
        unique=True,
        postgresql_where=sa.text("is_encrypted"),
    )
    op.create_table(
        "collection_chat_epochs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_kid", sa.String(length=128), nullable=False),
        sa.Column(
            "reason",
            sa.String(length=64),
            server_default="enabled",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["document_collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "epoch", name="uq_collection_chat_epoch"),
    )
    op.create_index(
        "ix_collection_chat_epochs_collection_id",
        "collection_chat_epochs",
        ["collection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_chat_epochs_collection_id", table_name="collection_chat_epochs")
    op.drop_table("collection_chat_epochs")
    op.drop_index("uq_collection_chat_epoch_idx", table_name="collection_chat_messages")
    op.drop_index("ix_collection_chat_messages_message_hash", table_name="collection_chat_messages")
    op.drop_column("collection_chat_messages", "message_hash")
    op.drop_column("collection_chat_messages", "crypto_idx")
    op.drop_column("collection_chat_messages", "crypto_epoch")
    op.drop_column("collection_chat_messages", "is_encrypted")
    op.drop_column("document_collections", "chat_encryption_enabled")
