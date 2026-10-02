"""Add durable per-tenant storage allocations and backfill existing tenants."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260924_0001"
down_revision = "20260923_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_storage_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("plan_id", sa.String(32), nullable=False),
        sa.Column("allocated_bytes", sa.BigInteger(), nullable=False),
        sa.Column("measured_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_tenant_storage_allocations_tenant_id",
        "tenant_storage_allocations",
        ["tenant_id"],
        unique=True,
    )
    op.create_index(
        "ix_tenant_storage_allocations_plan_id",
        "tenant_storage_allocations",
        ["plan_id"],
    )
    op.execute(sa.text("""
            INSERT INTO tenant_storage_allocations
                (id, tenant_id, plan_id, allocated_bytes, measured_bytes, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                t.id,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM user_roles ur
                        JOIN roles r ON r.id = ur.role_id
                        WHERE ur.tenant_id = t.id
                          AND r.name IN ('admin', 'super_admin')
                    ) THEN 'admin'
                    WHEN EXISTS (
                        SELECT 1
                        FROM user_roles ur
                        JOIN roles r ON r.id = ur.role_id
                        WHERE ur.tenant_id = t.id
                          AND r.name = 'editor'
                    ) THEN 'editor'
                    ELSE 'free'
                END,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM user_roles ur
                        JOIN roles r ON r.id = ur.role_id
                        WHERE ur.tenant_id = t.id
                          AND r.name IN ('admin', 'super_admin', 'editor')
                    ) THEN 1073741824
                    ELSE 524288000
                END,
                0,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM tenants t
            """))


def downgrade() -> None:
    op.drop_index("ix_tenant_storage_allocations_plan_id", table_name="tenant_storage_allocations")
    op.drop_index(
        "ix_tenant_storage_allocations_tenant_id", table_name="tenant_storage_allocations"
    )
    op.drop_table("tenant_storage_allocations")
