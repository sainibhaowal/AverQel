"""Clear legacy unapproved MCP registry intake rows.

The catalog table remains in place for the approved Google Workspace catalog.
This migration intentionally removes only rows that were never approved; it
does not touch tenant-owned servers, encrypted tokens, or audit events.
"""

from alembic import op

revision = "20260720_0002"
down_revision = ("20260720_0001", "20260716_0004")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM mcp_registry_entries " "WHERE trust_status IS DISTINCT FROM 'approved'")


def downgrade() -> None:
    raise RuntimeError(
        "The legacy unapproved MCP registry rows were intentionally deleted "
        "and cannot be restored by migration."
    )
