"""Add non-destructive quota reservations and archive/reconciliation metadata."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260926_0001"
down_revision = "20260925_0001"
branch_labels = None
depends_on = None


def _tenant_policy(table: str, name: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {name} ON {table}
        USING (current_setting('app.tenant_id', true) = 'bypass'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)""")


def upgrade() -> None:
    op.create_table(
        "storage_quota_reservations",
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
        sa.Column("reservation_key", sa.String(255), nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "reservation_key", name="uq_storage_quota_reservation_key"
        ),
    )
    op.create_index(
        "ix_storage_quota_reservations_tenant_id", "storage_quota_reservations", ["tenant_id"]
    )
    op.create_index(
        "ix_storage_quota_reservations_owner_user_id",
        "storage_quota_reservations",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_storage_quota_reservations_status", "storage_quota_reservations", ["status"]
    )
    op.create_index(
        "ix_storage_quota_reservations_expires_at", "storage_quota_reservations", ["expires_at"]
    )

    op.create_table(
        "storage_archive_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default=sa.text("'archived'")),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "lifecycle_item_id", name="uq_storage_archive_manifest_item"
        ),
    )
    op.create_index(
        "ix_storage_archive_manifests_tenant_id", "storage_archive_manifests", ["tenant_id"]
    )
    op.create_index(
        "ix_storage_archive_manifests_lifecycle_item_id",
        "storage_archive_manifests",
        ["lifecycle_item_id"],
    )
    op.create_index("ix_storage_archive_manifests_state", "storage_archive_manifests", ["state"])

    op.create_table(
        "storage_reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "category_totals_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("mismatch_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_storage_reconciliation_runs_tenant_id", "storage_reconciliation_runs", ["tenant_id"]
    )
    op.create_index(
        "ix_storage_reconciliation_runs_status", "storage_reconciliation_runs", ["status"]
    )
    for table, name in (
        ("storage_lifecycle_items", "tenant_isolation_storage_lifecycle_items"),
        ("storage_retention_runs", "tenant_isolation_storage_retention_runs"),
        ("storage_retention_decisions", "tenant_isolation_storage_retention_decisions"),
        ("storage_quota_reservations", "tenant_isolation_storage_quota_reservations"),
        ("storage_archive_manifests", "tenant_isolation_storage_archive_manifests"),
        ("storage_reconciliation_runs", "tenant_isolation_storage_reconciliation_runs"),
    ):
        _tenant_policy(table, name)


def downgrade() -> None:
    for table, name in (
        ("storage_retention_decisions", "tenant_isolation_storage_retention_decisions"),
        ("storage_retention_runs", "tenant_isolation_storage_retention_runs"),
        ("storage_lifecycle_items", "tenant_isolation_storage_lifecycle_items"),
        ("storage_reconciliation_runs", "tenant_isolation_storage_reconciliation_runs"),
        ("storage_archive_manifests", "tenant_isolation_storage_archive_manifests"),
        ("storage_quota_reservations", "tenant_isolation_storage_quota_reservations"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("storage_reconciliation_runs")
    op.drop_table("storage_archive_manifests")
    op.drop_table("storage_quota_reservations")
