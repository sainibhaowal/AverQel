"""normalize collection permissions to owner/shared

Revision ID: 20260402_0014
Revises: 20260402_0013
Create Date: 2026-04-02 00:30:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260402_0014"
down_revision = "20260402_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE collection_permissions
        SET role = CASE
            WHEN role = 'admin' THEN 'owner'
            WHEN role IN ('viewer', 'editor') THEN 'shared'
            ELSE role
        END
        """)
    op.execute("""
        ALTER TABLE collection_permissions
        ALTER COLUMN role SET DEFAULT 'shared'
        """)


def downgrade() -> None:
    op.execute("""
        UPDATE collection_permissions
        SET role = CASE
            WHEN role = 'owner' THEN 'admin'
            WHEN role = 'shared' THEN 'viewer'
            ELSE role
        END
        """)
    op.execute("""
        ALTER TABLE collection_permissions
        ALTER COLUMN role SET DEFAULT 'viewer'
        """)
