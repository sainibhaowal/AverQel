"""Add retention protections and a nullable DeepSpace event/run link.

This migration is additive. Existing event rows receive a NULL run_id and are
treated as unresolved by retention, so no legacy event is guessed safe.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260928_0001"
down_revision = "20260927_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deepspace_run_events",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deepspace_agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_deepspace_run_events_run_id", "deepspace_run_events", ["run_id"])
    for name in ("pinned", "legal_hold", "admin_exempt"):
        op.add_column(
            "storage_lifecycle_items",
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.create_index(f"ix_storage_lifecycle_items_{name}", "storage_lifecycle_items", [name])


def downgrade() -> None:
    for name in ("admin_exempt", "legal_hold", "pinned"):
        op.drop_index(f"ix_storage_lifecycle_items_{name}", table_name="storage_lifecycle_items")
        op.drop_column("storage_lifecycle_items", name)
    op.drop_index("ix_deepspace_run_events_run_id", table_name="deepspace_run_events")
    op.drop_column("deepspace_run_events", "run_id")
