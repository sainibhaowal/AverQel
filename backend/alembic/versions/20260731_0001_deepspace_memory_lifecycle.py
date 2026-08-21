"""add DeepSpace memory lifecycle and consent controls

Revision ID: 20260731_0001
Revises: 20260728_0001
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260731_0001"
down_revision = "20260728_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_memory",
        sa.Column(
            "confidence_score",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
    )
    op.add_column(
        "agent_memory",
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'active'")),
    )
    op.add_column("agent_memory", sa.Column("source", sa.String(), nullable=True))
    op.add_column("agent_memory", sa.Column("conversation_id", sa.String(), nullable=True))
    op.add_column("agent_memory", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_agent_memory_status", "agent_memory", ["status"], unique=False)
    op.create_index(
        "ix_agent_memory_conversation_id",
        "agent_memory",
        ["conversation_id"],
        unique=False,
    )
    op.create_index("ix_agent_memory_expires_at", "agent_memory", ["expires_at"], unique=False)

    op.create_table(
        "agent_memory_preferences",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "automatic_capture_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "review_inferred_memories",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "memory_retrieval_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_agent_memory_preferences_owner"),
    )
    op.create_index(
        "ix_agent_memory_preferences_tenant_id",
        "agent_memory_preferences",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_memory_preferences_user_id",
        "agent_memory_preferences",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_memory_preferences_user_id", table_name="agent_memory_preferences")
    op.drop_index("ix_agent_memory_preferences_tenant_id", table_name="agent_memory_preferences")
    op.drop_table("agent_memory_preferences")
    op.drop_index("ix_agent_memory_expires_at", table_name="agent_memory")
    op.drop_index("ix_agent_memory_conversation_id", table_name="agent_memory")
    op.drop_index("ix_agent_memory_status", table_name="agent_memory")
    op.drop_column("agent_memory", "expires_at")
    op.drop_column("agent_memory", "conversation_id")
    op.drop_column("agent_memory", "source")
    op.drop_column("agent_memory", "status")
    op.drop_column("agent_memory", "confidence_score")
