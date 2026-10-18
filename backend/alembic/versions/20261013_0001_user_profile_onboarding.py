"""Add user display names and first-run onboarding state."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261013_0001"
down_revision = "20261012_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=48), nullable=True))
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE users SET onboarding_completed_at = created_at "
        "WHERE onboarding_completed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "display_name")
