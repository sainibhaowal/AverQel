"""add durable DeepSpace agent runtime state

Revision ID: 20260726_0002
Revises: 20260726_0001
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260726_0002"
down_revision = "20260726_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_agent_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("assistant_message_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "user_id", "conversation_id", "status"):
        op.create_index(
            f"ix_deepspace_agent_runs_{column}", "deepspace_agent_runs", [column], unique=False
        )

    op.create_table(
        "deepspace_agent_steps",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=40), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("tool_call_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("run_id", "tenant_id", "user_id", "conversation_id", "sequence"):
        op.create_index(
            f"ix_deepspace_agent_steps_{column}", "deepspace_agent_steps", [column], unique=False
        )


def downgrade() -> None:
    op.drop_table("deepspace_agent_steps")
    op.drop_table("deepspace_agent_runs")
