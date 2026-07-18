"""add conversation kind for deepspace

Revision ID: c3d4e5f60718
Revises: 20260407_0019
Create Date: 2026-04-09 04:50:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d4e5f60718"
down_revision = "20260407_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("conversations")}
    indexes = {index["name"] for index in inspector.get_indexes("conversations")}

    if "kind" not in columns:
        op.add_column(
            "conversations",
            sa.Column(
                "kind",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'query'"),
            ),
        )

    if op.f("ix_conversations_kind") not in indexes:
        op.create_index(
            op.f("ix_conversations_kind"),
            "conversations",
            ["kind"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("conversations")}
    indexes = {index["name"] for index in inspector.get_indexes("conversations")}

    if op.f("ix_conversations_kind") in indexes:
        op.drop_index(op.f("ix_conversations_kind"), table_name="conversations")

    if "kind" in columns:
        op.drop_column("conversations", "kind")
