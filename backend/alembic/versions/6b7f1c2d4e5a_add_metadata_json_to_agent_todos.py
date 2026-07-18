"""add metadata_json to agent_todos

Revision ID: 6b7f1c2d4e5a
Revises: f1fd04b30874
Create Date: 2026-05-07 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "6b7f1c2d4e5a"
down_revision = "f1fd04b30874"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_todos", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.add_column("agent_todos", sa.Column("automation_json", sa.JSON(), nullable=True))
    op.add_column("agent_todos", sa.Column("is_recurring", sa.Integer(), nullable=True))
    op.add_column("agent_todos", sa.Column("enabled", sa.Integer(), nullable=True))
    op.add_column("agent_todos", sa.Column("next_run_at", sa.DateTime(), nullable=True))
    op.add_column("agent_todos", sa.Column("last_run_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_todos", "last_run_at")
    op.drop_column("agent_todos", "next_run_at")
    op.drop_column("agent_todos", "enabled")
    op.drop_column("agent_todos", "is_recurring")
    op.drop_column("agent_todos", "automation_json")
    op.drop_column("agent_todos", "metadata_json")
