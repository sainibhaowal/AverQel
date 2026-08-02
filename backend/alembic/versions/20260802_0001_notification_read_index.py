"""Add the notification-feed index used by the dashboard bell.

Revision ID: 20260802_0001
Revises: 20260731_0001
Create Date: 2026-08-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260802_0001"
down_revision = "20260731_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CONCURRENTLY avoids blocking notification reads or writes on a populated
    # production database.  The statement must run outside Alembic's default
    # transaction for PostgreSQL.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_collection_notifications_recipient_created_id "
            "ON collection_notifications (recipient_user_id, created_at DESC, id DESC)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS "
            "ix_collection_notifications_recipient_created_id"
        )
