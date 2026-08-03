"""Make connected MCP accounts available across DeepSpace conversations.

Revision ID: 20260803_0001
Revises: 20260802_0001
Create Date: 2026-08-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260803_0001"
down_revision = "20260802_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "mcp_connection_policies",
        "default_enabled",
        server_default="true",
    )
    # Existing connected accounts were created under the old manual-scope
    # default. Activate only currently connected/enabled servers; disconnected
    # accounts remain inactive until the user reconnects them.
    op.execute(
        "UPDATE mcp_connection_policies AS policy "
        "SET default_enabled = TRUE "
        "FROM mcp_servers AS server "
        "WHERE policy.server_id = server.id "
        "AND server.enabled = TRUE "
        "AND server.status = 'connected'"
    )


def downgrade() -> None:
    op.alter_column(
        "mcp_connection_policies",
        "default_enabled",
        server_default="false",
    )
