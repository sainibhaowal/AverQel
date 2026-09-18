"""Add cascade foreign key constraints from DeepSpace runtime and snapshots to conversations.

Revision ID: 20260917_0001
Revises: 20260916_0002
"""

from __future__ import annotations

from alembic import op

revision = "20260917_0001"
down_revision = "20260916_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Clean up any existing orphaned rows before adding the foreign key constraints.
    op.execute(
        "DELETE FROM deepspace_agent_steps WHERE conversation_id NOT IN (SELECT id FROM conversations)"
    )
    op.execute(
        "DELETE FROM deepspace_run_events WHERE conversation_id NOT IN (SELECT id FROM conversations)"
    )
    op.execute(
        "DELETE FROM deepspace_agent_runs WHERE conversation_id NOT IN (SELECT id FROM conversations)"
    )
    op.execute(
        "DELETE FROM deepspace_mission_snapshots WHERE conversation_id IS NOT NULL AND conversation_id NOT IN (SELECT id FROM conversations)"
    )

    # 2. Add ON DELETE CASCADE foreign key constraints.
    op.create_foreign_key(
        "fk_deepspace_agent_runs_conversation_id",
        "deepspace_agent_runs",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_deepspace_agent_steps_conversation_id",
        "deepspace_agent_steps",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_deepspace_run_events_conversation_id",
        "deepspace_run_events",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_deepspace_mission_snapshots_conversation_id",
        "deepspace_mission_snapshots",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_deepspace_mission_snapshots_conversation_id",
        "deepspace_mission_snapshots",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_deepspace_run_events_conversation_id",
        "deepspace_run_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_deepspace_agent_steps_conversation_id",
        "deepspace_agent_steps",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_deepspace_agent_runs_conversation_id",
        "deepspace_agent_runs",
        type_="foreignkey",
    )
