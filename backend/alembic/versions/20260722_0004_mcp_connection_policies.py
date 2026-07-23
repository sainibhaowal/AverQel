"""Add tenant-scoped MCP connection policy storage with RLS."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260722_0004"
down_revision = "20260722_0003"
branch_labels = None
depends_on = None


def _jsonb_default(value: str) -> sa.TextClause:
    return sa.text(f"'{value}'::jsonb")


def _tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid)
        """
    )


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "mcp_connection_policies",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", uuid, sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allowed_tools", jsonb, nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("denied_tools", jsonb, nullable=False, server_default=_jsonb_default("[]")),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("risk_ceiling", sa.String(32), nullable=False, server_default=sa.text("'read'")),
        sa.Column(
            "approval_rules",
            jsonb,
            nullable=False,
            server_default=_jsonb_default('{"write":"needs_approval","delete":"needs_approval","external_message":"needs_approval"}'),
        ),
        sa.Column("tool_modes", jsonb, nullable=False, server_default=_jsonb_default("{}")),
        sa.Column("default_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deepspace_overrides", jsonb, nullable=False, server_default=_jsonb_default("{}")),
        sa.Column("conversation_overrides", jsonb, nullable=False, server_default=_jsonb_default("{}")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("server_id", name="uq_mcp_connection_policies_server_id"),
        sa.CheckConstraint(
            "risk_ceiling IN ('read', 'write', 'delete', 'external_message')",
            name="ck_mcp_connection_policies_risk_ceiling",
        ),
    )
    for column in ("tenant_id", "user_id", "server_id", "updated_at"):
        op.create_index(f"ix_mcp_connection_policies_{column}", "mcp_connection_policies", [column])
    _tenant_rls("mcp_connection_policies")

    # The FK on MCPServer is added after the policy table exists. It remains
    # nullable so existing connections retain their current behavior.
    op.add_column(
        "mcp_servers",
        sa.Column("connection_policy_id", uuid, nullable=True),
    )
    op.create_foreign_key(
        "fk_mcp_servers_connection_policy_id",
        "mcp_servers",
        "mcp_connection_policies",
        ["connection_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mcp_servers_connection_policy_id", "mcp_servers", ["connection_policy_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_servers_connection_policy_id", table_name="mcp_servers")
    op.drop_constraint("fk_mcp_servers_connection_policy_id", "mcp_servers", type_="foreignkey")
    op.drop_column("mcp_servers", "connection_policy_id")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_mcp_connection_policies ON mcp_connection_policies")
    op.execute("ALTER TABLE mcp_connection_policies NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mcp_connection_policies DISABLE ROW LEVEL SECURITY")
    for column in ("updated_at", "server_id", "user_id", "tenant_id"):
        op.drop_index(f"ix_mcp_connection_policies_{column}", table_name="mcp_connection_policies")
    op.drop_table("mcp_connection_policies")
