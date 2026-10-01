"""Track collection chat media ownership and cleanup lifecycle."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0002"
down_revision = "20261012_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_chat_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="uploaded", nullable=False),
        sa.Column("attached_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["document_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["attached_message_id"], ["collection_chat_messages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "object_key", name="uq_collection_chat_media_object"),
    )
    for name, column in (
        ("ix_collection_chat_media_collection_id", "collection_id"),
        ("ix_collection_chat_media_tenant_id", "tenant_id"),
        ("ix_collection_chat_media_uploaded_by_user_id", "uploaded_by_user_id"),
        ("ix_collection_chat_media_status", "status"),
        ("ix_collection_chat_media_attached_message_id", "attached_message_id"),
    ):
        op.create_index(name, "collection_chat_media", [column])
    op.add_column(
        "collection_chat_messages",
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_collection_chat_messages_media_id", "collection_chat_messages", ["media_id"]
    )
    op.create_foreign_key(
        "fk_collection_chat_messages_media_id",
        "collection_chat_messages",
        "collection_chat_media",
        ["media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_collection_chat_messages_media_id", "collection_chat_messages", type_="foreignkey"
    )
    op.drop_index("ix_collection_chat_messages_media_id", table_name="collection_chat_messages")
    op.drop_column("collection_chat_messages", "media_id")
    for name in (
        "ix_collection_chat_media_attached_message_id",
        "ix_collection_chat_media_status",
        "ix_collection_chat_media_uploaded_by_user_id",
        "ix_collection_chat_media_tenant_id",
        "ix_collection_chat_media_collection_id",
    ):
        op.drop_index(name, table_name="collection_chat_media")
    op.drop_table("collection_chat_media")
