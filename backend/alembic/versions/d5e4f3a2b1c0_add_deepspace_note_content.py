"""add deepspace note content

Revision ID: d5e4f3a2b1c0
Revises: c3d4e5f60718
Create Date: 2026-04-16 19:10:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "d5e4f3a2b1c0"
down_revision = "c3d4e5f60718"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("conversations")}

    if "content_html" not in columns:
        op.add_column(
            "conversations", sa.Column("content_html", sa.Text(), nullable=True)
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("conversations")}

    if "content_html" in columns:
        op.drop_column("conversations", "content_html")
