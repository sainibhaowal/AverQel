"""add break glass grants

Revision ID: 20260425_0026
Revises: 20260424_0025
Create Date: 2026-04-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260425_0026"
down_revision: str | Sequence[str] | None = "20260424_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "break_glass_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_break_glass_grants_actor_user_id",
        "break_glass_grants",
        ["actor_user_id"],
    )
    op.create_index("ix_break_glass_grants_status", "break_glass_grants", ["status"])
    op.create_index(
        "ix_break_glass_grants_target_user_id",
        "break_glass_grants",
        ["target_user_id"],
    )
    op.create_index(
        "ix_break_glass_grants_tenant_id", "break_glass_grants", ["tenant_id"]
    )
    op.create_index(
        "ix_break_glass_grants_resource_type",
        "break_glass_grants",
        ["resource_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_break_glass_grants_resource_type", table_name="break_glass_grants"
    )
    op.drop_index("ix_break_glass_grants_tenant_id", table_name="break_glass_grants")
    op.drop_index(
        "ix_break_glass_grants_target_user_id", table_name="break_glass_grants"
    )
    op.drop_index("ix_break_glass_grants_status", table_name="break_glass_grants")
    op.drop_index(
        "ix_break_glass_grants_actor_user_id", table_name="break_glass_grants"
    )
    op.drop_table("break_glass_grants")
