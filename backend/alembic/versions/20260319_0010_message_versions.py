"""add message versions for chat regeneration

Revision ID: 20260319_0010
Revises: 20260310_0009
Create Date: 2026-03-19 12:00:00.000000
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260319_0010"
down_revision = "20260310_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    message_versions = sa.table(
        "message_versions",
        sa.column("id", sa.UUID()),
        sa.column("message_id", sa.UUID()),
        sa.column("version_index", sa.Integer()),
        sa.column("content", sa.Text()),
        sa.column("metadata_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("source_type", sa.String(length=32)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "message_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("version_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "version_index",
            name="uq_message_versions_message_idx",
        ),
    )
    op.create_index(
        op.f("ix_message_versions_message_id"),
        "message_versions",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        "ix_message_versions_message_id_version_index",
        "message_versions",
        ["message_id", "version_index"],
        unique=False,
    )
    op.add_column(
        "messages",
        sa.Column("active_version_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_messages_active_version_id"),
        "messages",
        ["active_version_id"],
        unique=False,
    )

    conn = op.get_bind()
    messages = conn.execute(
        sa.text(
            "SELECT id, content, metadata_json, created_at FROM messages ORDER BY created_at ASC"
        )
    ).mappings()
    for row in messages:
        version_id = uuid.uuid4()
        conn.execute(
            sa.insert(message_versions).values(
                id=version_id,
                message_id=row["id"],
                version_index=1,
                content=row["content"],
                metadata_json=row["metadata_json"] or {},
                source_type="initial",
                created_at=row["created_at"],
            )
        )
        conn.execute(
            sa.text(
                "UPDATE messages SET active_version_id = :active_version_id WHERE id = :message_id"
            ),
            {"active_version_id": version_id, "message_id": row["id"]},
        )

    op.create_foreign_key(
        "fk_messages_active_version_id",
        "messages",
        "message_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_active_version_id", "messages", type_="foreignkey")
    op.drop_index(op.f("ix_messages_active_version_id"), table_name="messages")
    op.drop_column("messages", "active_version_id")
    op.drop_index(
        "ix_message_versions_message_id_version_index",
        table_name="message_versions",
    )
    op.drop_index(op.f("ix_message_versions_message_id"), table_name="message_versions")
    op.drop_table("message_versions")
