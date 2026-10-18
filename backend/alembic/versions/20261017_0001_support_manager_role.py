"""Add a separately assigned support manager role."""

from __future__ import annotations

from alembic import op

revision = "20261017_0001"
down_revision = "20261016_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO roles (name, description)
        VALUES ('support_manager', 'Can review and respond to support tickets.')
        ON CONFLICT (name) DO NOTHING
        """)


def downgrade() -> None:
    # Keep role rows so existing assignments remain intact and fail closed if
    # an older application version does not map the role to permissions.
    pass
