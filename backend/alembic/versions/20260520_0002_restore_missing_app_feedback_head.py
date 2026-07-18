"""Restore missing app feedback migration head.

Revision ID: 20260520_0002
Revises: 20260510_0001
Create Date: 2026-05-20 00:02:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20260520_0002"
down_revision = "20260510_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Compatibility shim: the database is already stamped to this revision.
    # Keeping the node in the migration graph lets startup migrations resolve
    # cleanly without mutating the existing schema again.
    pass


def downgrade() -> None:
    pass
