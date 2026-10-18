"""Add explicit feedback and collection moderator roles."""

from __future__ import annotations

from alembic import op

revision = "20261016_0001"
down_revision = "20261013_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO roles (name, description)
        VALUES
            ('feedback_manager', 'Can review and respond to submitted product feedback.'),
            ('collection_moderator', 'Can review Qel Connect reports within the assigned tenant.')
        ON CONFLICT (name) DO NOTHING
        """)


def downgrade() -> None:
    # Role rows may have existed before this migration or be referenced by
    # explicit assignments. Retain them; the downgraded application has no
    # permissions mapped to these names, so assignments fail closed.
    pass
