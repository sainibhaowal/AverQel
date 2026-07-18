"""force personal provider scope

Revision ID: 20260425_0027
Revises: 20260425_0026
Create Date: 2026-04-25 16:45:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260425_0027"
down_revision: str | Sequence[str] | None = "20260425_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # User-owned provider records must never be shared by tenant/workspace.
    op.execute(sa.text("""
            UPDATE provider_configs
            SET workspace_id = NULL,
                visibility_scope = 'user'
            WHERE owner_user_id IS NOT NULL
            """))
    op.execute(sa.text("""
            UPDATE provider_assignments
            SET workspace_id = NULL,
                visibility_scope = 'user'
            WHERE owner_user_id IS NOT NULL
            """))

    # Legacy tenant/workspace provider records without an owner are left in the
    # database for audit/history, but are no longer visible to normal users.
    op.execute(sa.text("""
            UPDATE provider_configs
            SET visibility_scope = 'legacy_shared_disabled'
            WHERE owner_user_id IS NULL
              AND visibility_scope IN ('tenant', 'workspace')
              AND provider_type <> 'sentence-transformers'
            """))
    op.execute(sa.text("""
            UPDATE provider_assignments
            SET visibility_scope = 'legacy_shared_disabled'
            WHERE owner_user_id IS NULL
              AND visibility_scope IN ('tenant', 'workspace')
            """))


def downgrade() -> None:
    op.execute(sa.text("""
            UPDATE provider_configs
            SET visibility_scope = 'tenant'
            WHERE visibility_scope = 'legacy_shared_disabled'
            """))
    op.execute(sa.text("""
            UPDATE provider_assignments
            SET visibility_scope = 'tenant'
            WHERE visibility_scope = 'legacy_shared_disabled'
            """))
