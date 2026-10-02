"""Add durable, cascade-deleted DeepSpace context summaries."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260918_0001"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_conversation_context_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_message_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column(
            "summary_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("conversation_id", name="uq_deepspace_context_summary_conversation"),
    )
    for column in ("tenant_id", "user_id", "conversation_id"):
        op.create_index(
            f"ix_deepspace_context_summaries_{column}",
            "deepspace_conversation_context_summaries",
            [column],
        )


def downgrade() -> None:
    op.drop_table("deepspace_conversation_context_summaries")
