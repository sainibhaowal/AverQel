"""add user privacy scope to providers

Revision ID: 20260424_0025
Revises: 20260421_0024_merge_heads
Create Date: 2026-04-24 20:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260424_0025"
down_revision = "20260421_0024_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "provider_configs",
        sa.Column(
            "visibility_scope",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'tenant'"),
        ),
    )
    op.create_foreign_key(
        "fk_provider_configs_owner_user_id_users",
        "provider_configs",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_provider_configs_owner_user_id",
        "provider_configs",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_provider_configs_visibility_scope",
        "provider_configs",
        ["visibility_scope"],
    )
    op.drop_constraint(
        "uq_provider_configs_tenant_workspace_name",
        "provider_configs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_provider_configs_tenant_workspace_owner_name",
        "provider_configs",
        ["tenant_id", "workspace_id", "owner_user_id", "display_name"],
    )

    op.add_column(
        "provider_assignments",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "provider_assignments",
        sa.Column(
            "visibility_scope",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'tenant'"),
        ),
    )
    op.create_foreign_key(
        "fk_provider_assignments_owner_user_id_users",
        "provider_assignments",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_provider_assignments_owner_user_id",
        "provider_assignments",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_provider_assignments_visibility_scope",
        "provider_assignments",
        ["visibility_scope"],
    )
    op.drop_constraint(
        "uq_provider_assignments_scope_priority",
        "provider_assignments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_provider_assignments_owner_scope_priority",
        "provider_assignments",
        ["tenant_id", "workspace_id", "owner_user_id", "feature_scope", "priority"],
    )

    op.alter_column("provider_configs", "visibility_scope", server_default=None)
    op.alter_column("provider_assignments", "visibility_scope", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "uq_provider_assignments_owner_scope_priority",
        "provider_assignments",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_provider_assignments_scope_priority",
        "provider_assignments",
        ["tenant_id", "workspace_id", "feature_scope", "priority"],
    )
    op.drop_index(
        "ix_provider_assignments_visibility_scope",
        table_name="provider_assignments",
    )
    op.drop_index(
        "ix_provider_assignments_owner_user_id",
        table_name="provider_assignments",
    )
    op.drop_constraint(
        "fk_provider_assignments_owner_user_id_users",
        "provider_assignments",
        type_="foreignkey",
    )
    op.drop_column("provider_assignments", "visibility_scope")
    op.drop_column("provider_assignments", "owner_user_id")

    op.drop_constraint(
        "uq_provider_configs_tenant_workspace_owner_name",
        "provider_configs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_provider_configs_tenant_workspace_name",
        "provider_configs",
        ["tenant_id", "workspace_id", "display_name"],
    )
    op.drop_index("ix_provider_configs_visibility_scope", table_name="provider_configs")
    op.drop_index("ix_provider_configs_owner_user_id", table_name="provider_configs")
    op.drop_constraint(
        "fk_provider_configs_owner_user_id_users",
        "provider_configs",
        type_="foreignkey",
    )
    op.drop_column("provider_configs", "visibility_scope")
    op.drop_column("provider_configs", "owner_user_id")
