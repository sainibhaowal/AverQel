"""Track DeepSpace worker heartbeats for safe reconnects.

Revision ID: 20260808_0001
Revises: 20260806_0001
"""

import sqlalchemy as sa

from alembic import op

revision = "20260808_0001"
down_revision = "20260806_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deepspace_agent_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_deepspace_agent_runs_heartbeat_at",
        "deepspace_agent_runs",
        ["heartbeat_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_deepspace_agent_runs_heartbeat_at", table_name="deepspace_agent_runs")
    op.drop_column("deepspace_agent_runs", "heartbeat_at")
