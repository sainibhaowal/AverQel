"""Add durable scheduled-run history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260913_0003"
down_revision = "20260913_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_schedule_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deepspace_schedules.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("request_id", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_deepspace_schedule_runs_schedule_id", "deepspace_schedule_runs", ["schedule_id"]
    )
    op.create_index(
        "ix_deepspace_schedule_runs_tenant_id", "deepspace_schedule_runs", ["tenant_id"]
    )
    op.create_index("ix_deepspace_schedule_runs_status", "deepspace_schedule_runs", ["status"])


def downgrade() -> None:
    op.drop_table("deepspace_schedule_runs")
