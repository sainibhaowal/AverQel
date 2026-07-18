"""Add the nullable user avatar column expected by the auth model."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260713_0003"
down_revision = ("1a2b3c4d5e6f", "20260522_0003", "20260606_0001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "avatar" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "avatar" in {column["name"] for column in inspector.get_columns("users")}:
        op.drop_column("users", "avatar")
