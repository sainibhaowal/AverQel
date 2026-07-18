"""create week4 security and reliability tables

Revision ID: 20260221_0005
Revises: 20260221_0004
Create Date: 2026-02-21 00:00:03
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260221_0005"
down_revision = "20260221_0004"
branch_labels = None
depends_on = None


def _create_rls_policy(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation_{table_name}
        ON {table_name}
        USING (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        """)


def _drop_rls_policy(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'success'"),
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_audit_logs_tenant_created_at", "audit_logs", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_audit_logs_tenant_action_created_at",
        "audit_logs",
        ["tenant_id", "action", "created_at"],
    )

    op.create_table(
        "data_deletions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "scope",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'tenant_data'"),
        ),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "result_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_data_deletions_tenant_requested_at",
        "data_deletions",
        ["tenant_id", "requested_at"],
    )
    op.create_index(
        "ix_data_deletions_tenant_status_requested_at",
        "data_deletions",
        ["tenant_id", "status", "requested_at"],
    )

    _create_rls_policy("audit_logs")
    _create_rls_policy("data_deletions")


def downgrade() -> None:
    _drop_rls_policy("data_deletions")
    _drop_rls_policy("audit_logs")

    op.drop_index(
        "ix_data_deletions_tenant_status_requested_at", table_name="data_deletions"
    )
    op.drop_index("ix_data_deletions_tenant_requested_at", table_name="data_deletions")
    op.drop_table("data_deletions")

    op.drop_index("ix_audit_logs_tenant_action_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_tenant_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
