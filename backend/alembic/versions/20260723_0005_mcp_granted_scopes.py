"""Store verified MCP OAuth scopes without changing encrypted credentials."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260723_0005"
down_revision = "20260722_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_oauth_tokens",
        sa.Column(
            "granted_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_oauth_tokens", "granted_scopes")
