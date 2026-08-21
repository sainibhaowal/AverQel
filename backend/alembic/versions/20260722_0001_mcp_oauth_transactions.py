"""store native MCP OAuth transactions encrypted and single-use"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260722_0001"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        """)


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "mcp_oauth_transactions",
        sa.Column("id", uuid, primary_key=True),
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
        sa.Column(
            "server_id",
            uuid,
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("secret_kid", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("state_hash", name="uq_mcp_oauth_transactions_state_hash"),
    )
    for column in ("tenant_id", "user_id", "server_id", "expires_at", "consumed_at"):
        op.create_index(f"ix_mcp_oauth_transactions_{column}", "mcp_oauth_transactions", [column])
    _tenant_rls("mcp_oauth_transactions")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation_mcp_oauth_transactions ON mcp_oauth_transactions"
    )
    op.execute("ALTER TABLE mcp_oauth_transactions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mcp_oauth_transactions DISABLE ROW LEVEL SECURITY")
    op.drop_table("mcp_oauth_transactions")
