"""Add the additive Storage retention policy and lifecycle registry.

This migration adds metadata only.  It does not move, hide, archive, or delete
any existing content.  Existing tenants default to retention ``off``.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260925_0001"
down_revision = "20260924_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_storage_allocations",
        sa.Column("retention_mode", sa.String(8), nullable=False, server_default=sa.text("'off'")),
    )
    op.add_column(
        "tenant_storage_allocations",
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "tenant_storage_allocations",
        sa.Column(
            "retention_policy_version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    op.add_column(
        "tenant_storage_allocations",
        sa.Column("retention_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_tenant_storage_retention_mode",
        "tenant_storage_allocations",
        "retention_mode IN ('off', '30', '60', '90')",
    )
    op.create_check_constraint(
        "ck_tenant_storage_retention_days",
        "tenant_storage_allocations",
        "retention_days IN (0, 30, 60, 90)",
    )

    op.create_table(
        "storage_lifecycle_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_meaningful_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_kind", sa.String(64), nullable=True),
        sa.Column("dependency_group_id", sa.String(255), nullable=True),
        sa.Column("protected_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protection_reason", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "category",
            "source_type",
            "source_id",
            name="uq_storage_lifecycle_item_identity",
        ),
    )
    op.create_index(
        "ix_storage_lifecycle_items_tenant_id", "storage_lifecycle_items", ["tenant_id"]
    )
    op.create_index(
        "ix_storage_lifecycle_items_owner_user_id", "storage_lifecycle_items", ["owner_user_id"]
    )
    op.create_index("ix_storage_lifecycle_items_category", "storage_lifecycle_items", ["category"])
    op.create_index("ix_storage_lifecycle_items_state", "storage_lifecycle_items", ["state"])
    op.create_index(
        "ix_storage_lifecycle_items_last_activity",
        "storage_lifecycle_items",
        ["last_meaningful_activity_at"],
    )
    op.create_index(
        "ix_storage_lifecycle_items_dependency_group",
        "storage_lifecycle_items",
        ["dependency_group_id"],
    )

    op.create_table(
        "storage_retention_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("retention_mode", sa.String(8), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("protected_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("legacy_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_storage_retention_runs_tenant_id", "storage_retention_runs", ["tenant_id"])
    op.create_index("ix_storage_retention_runs_status", "storage_retention_runs", ["status"])

    op.create_table(
        "storage_retention_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("storage_retention_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lifecycle_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("storage_lifecycle_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(120), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "run_id", "lifecycle_item_id", "action", name="uq_storage_retention_decision"
        ),
    )
    op.create_index(
        "ix_storage_retention_decisions_run_id", "storage_retention_decisions", ["run_id"]
    )
    op.create_index(
        "ix_storage_retention_decisions_tenant_id", "storage_retention_decisions", ["tenant_id"]
    )
    op.create_index(
        "ix_storage_retention_decisions_lifecycle_item_id",
        "storage_retention_decisions",
        ["lifecycle_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_storage_retention_decisions_lifecycle_item_id", table_name="storage_retention_decisions"
    )
    op.drop_index(
        "ix_storage_retention_decisions_tenant_id", table_name="storage_retention_decisions"
    )
    op.drop_index("ix_storage_retention_decisions_run_id", table_name="storage_retention_decisions")
    op.drop_table("storage_retention_decisions")
    op.drop_index("ix_storage_retention_runs_status", table_name="storage_retention_runs")
    op.drop_index("ix_storage_retention_runs_tenant_id", table_name="storage_retention_runs")
    op.drop_table("storage_retention_runs")
    op.drop_index(
        "ix_storage_lifecycle_items_dependency_group", table_name="storage_lifecycle_items"
    )
    op.drop_index("ix_storage_lifecycle_items_last_activity", table_name="storage_lifecycle_items")
    op.drop_index("ix_storage_lifecycle_items_state", table_name="storage_lifecycle_items")
    op.drop_index("ix_storage_lifecycle_items_category", table_name="storage_lifecycle_items")
    op.drop_index("ix_storage_lifecycle_items_owner_user_id", table_name="storage_lifecycle_items")
    op.drop_index("ix_storage_lifecycle_items_tenant_id", table_name="storage_lifecycle_items")
    op.drop_table("storage_lifecycle_items")
    op.drop_constraint(
        "ck_tenant_storage_retention_days", "tenant_storage_allocations", type_="check"
    )
    op.drop_constraint(
        "ck_tenant_storage_retention_mode", "tenant_storage_allocations", type_="check"
    )
    op.drop_column("tenant_storage_allocations", "retention_updated_at")
    op.drop_column("tenant_storage_allocations", "retention_policy_version")
    op.drop_column("tenant_storage_allocations", "retention_days")
    op.drop_column("tenant_storage_allocations", "retention_mode")
