"""Add one connection-level default MCP tool permission mode."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260818_0001"
down_revision = "20260816_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_connection_policies",
        sa.Column(
            "default_tool_mode",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'needs_approval'"),
        ),
    )
    op.create_check_constraint(
        "ck_mcp_connection_policies_default_tool_mode",
        "mcp_connection_policies",
        "default_tool_mode IN ('always_allow', 'needs_approval', 'blocked')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_mcp_connection_policies_default_tool_mode",
        "mcp_connection_policies",
        type_="check",
    )
    op.drop_column("mcp_connection_policies", "default_tool_mode")
