"""Persist tenant-validated document comment mentions."""

import sqlalchemy as sa

from alembic import op

revision = "20261008_0001"
down_revision = "20261007_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "comments", sa.Column("mentions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("comments", "mentions")
