"""prevent duplicate event sequence numbers per MCP server"""

from alembic import op

revision = "20260716_0002"
down_revision = "20260716_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_mcp_events_server_sequence", "mcp_events", ["server_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_mcp_events_server_sequence", "mcp_events", type_="unique")
