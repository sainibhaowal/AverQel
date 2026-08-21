from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260715_0004"
down_revision = "20260713_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_mission_snapshots",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_deepspace_mission_snapshots_tenant_id",
        "deepspace_mission_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_deepspace_mission_snapshots_user_id",
        "deepspace_mission_snapshots",
        ["user_id"],
    )
    op.create_index(
        "ix_deepspace_mission_snapshots_status",
        "deepspace_mission_snapshots",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deepspace_mission_snapshots_status",
        table_name="deepspace_mission_snapshots",
    )
    op.drop_index(
        "ix_deepspace_mission_snapshots_user_id",
        table_name="deepspace_mission_snapshots",
    )
    op.drop_index(
        "ix_deepspace_mission_snapshots_tenant_id",
        table_name="deepspace_mission_snapshots",
    )
    op.drop_table("deepspace_mission_snapshots")
