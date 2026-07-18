"""add durable native MCP runtime tables"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260716_0001"
down_revision = "20260715_0004"
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
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "mcp_servers",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("transport", sa.String(32), nullable=False),
        sa.Column("config", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'disconnected'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_error", sa.String(1000)),
        sa.Column("reconnect_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_connected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_mcp_servers_tenant_id", "mcp_servers", ["tenant_id"])
    op.create_index("ix_mcp_servers_user_id", "mcp_servers", ["user_id"])
    op.create_index("ix_mcp_servers_status", "mcp_servers", ["status"])
    op.create_table(
        "mcp_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("server_id", uuid, sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("payload", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_mcp_events_tenant_id", "mcp_events", ["tenant_id"])
    op.create_index("ix_mcp_events_user_id", "mcp_events", ["user_id"])
    op.create_index("ix_mcp_events_server_id", "mcp_events", ["server_id"])
    op.create_index("ix_mcp_events_event_type", "mcp_events", ["event_type"])
    op.create_index("ix_mcp_events_created_at", "mcp_events", ["created_at"])
    op.create_table(
        "mcp_oauth_tokens",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", uuid, sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("secret_kid", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_mcp_oauth_tokens_tenant_id", "mcp_oauth_tokens", ["tenant_id"])
    for table in ("mcp_servers", "mcp_events", "mcp_oauth_tokens"):
        _tenant_rls(table)


def downgrade() -> None:
    for table in ("mcp_oauth_tokens", "mcp_events", "mcp_servers"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("mcp_oauth_tokens")
    op.drop_table("mcp_events")
    op.drop_table("mcp_servers")
