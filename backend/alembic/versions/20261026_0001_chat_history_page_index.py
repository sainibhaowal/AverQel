"""Index chronological chat history pages.

Revision ID: 20261026_0001
Revises: 20261019_0004
Create Date: 2026-10-26 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20261026_0001"
down_revision = "20261019_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep chat reads and writes available while the index is built on existing
    # production history. PostgreSQL requires this statement outside the
    # migration transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_messages_conversation_created_id "
            "ON messages (conversation_id, created_at, id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_messages_conversation_created_id")
