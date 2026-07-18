from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260402_0017"
down_revision = "20260402_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
            WITH first_members AS (
                SELECT DISTINCT ON (cp.collection_id)
                    cp.id,
                    cp.collection_id
                FROM collection_permissions cp
                WHERE cp.role IN ('member', 'shared', 'owner')
                ORDER BY cp.collection_id, cp.created_at ASC, cp.id ASC
            )
            UPDATE collection_permissions target
            SET role = 'owner'
            FROM first_members fm
            WHERE target.id = fm.id
              AND NOT EXISTS (
                  SELECT 1
                  FROM collection_permissions existing_owner
                  WHERE existing_owner.collection_id = fm.collection_id
                    AND existing_owner.role = 'owner'
              )
            """))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
            UPDATE collection_permissions
            SET role = 'member'
            WHERE role = 'owner'
            """))
