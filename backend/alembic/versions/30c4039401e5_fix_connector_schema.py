"""fix_connector_schema

Revision ID: 30c4039401e5
Revises: f1fd04b30874
Create Date: 2026-05-06 16:27:22.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "30c4039401e5"
down_revision = "f1fd04b30874"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add user_id to connectors
    op.add_column("connectors", sa.Column("user_id", sa.UUID(), nullable=False))
    op.create_index(
        op.f("ix_connectors_user_id"), "connectors", ["user_id"], unique=False
    )
    op.create_foreign_key(
        None, "connectors", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # 2. Update lengths to match models
    op.alter_column(
        "connectors",
        "sync_frequency",
        existing_type=sa.VARCHAR(length=32),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "connectors",
        "last_error",
        existing_type=sa.TEXT(),
        type_=sa.String(length=500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.drop_constraint(None, "connectors", type_="foreignkey")
    op.drop_index(op.f("ix_connectors_user_id"), table_name="connectors")
    op.drop_column("connectors", "user_id")
