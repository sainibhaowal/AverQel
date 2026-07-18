"""agent runtime preferences

Revision ID: 20260522_0003
Revises: 20260520_0002
Create Date: 2026-05-22 11:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260522_0003"
down_revision = "20260520_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_preferences",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("preference_key", sa.String(), nullable=False),
        sa.Column("preference_value", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "conversation_id",
            "preference_key",
            name="uq_agent_runtime_preference_scope_key",
        ),
    )
    op.create_index(
        op.f("ix_agent_runtime_preferences_conversation_id"),
        "agent_runtime_preferences",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_preferences_id"),
        "agent_runtime_preferences",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_preferences_preference_key"),
        "agent_runtime_preferences",
        ["preference_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_preferences_tenant_id"),
        "agent_runtime_preferences",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_runtime_preferences_user_id"),
        "agent_runtime_preferences",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("agent_runtime_preferences")
