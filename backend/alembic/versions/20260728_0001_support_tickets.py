"""create tenant-scoped support ticket storage

Revision ID: 20260728_0001
Revises: 20260726_0002
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260728_0001"
down_revision = "20260726_0002"
branch_labels = None
depends_on = None


def _enable_tenant_rls() -> None:
    op.execute("ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_tickets FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation_support_tickets ON support_tickets
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        """)


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "support_tickets",
        sa.Column(
            "id",
            uuid,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            uuid,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'query'"),
        ),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
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

    for column in ("tenant_id", "user_id", "category", "status"):
        op.create_index(
            f"ix_support_tickets_{column}",
            "support_tickets",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_support_tickets_user_created_at",
        "support_tickets",
        ["user_id", "created_at"],
        unique=False,
    )
    _enable_tenant_rls()


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_support_tickets ON support_tickets")
    op.execute("ALTER TABLE support_tickets NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_tickets DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_support_tickets_user_created_at", table_name="support_tickets")
    for column in ("status", "category", "user_id", "tenant_id"):
        op.drop_index(f"ix_support_tickets_{column}", table_name="support_tickets")
    op.drop_table("support_tickets")
