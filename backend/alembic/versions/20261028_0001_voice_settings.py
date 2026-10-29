"""Create voice settings table.

Revision ID: 20261028_0001
Revises: 20261026_0001
Create Date: 2026-10-28 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261028_0001"
down_revision = "20261026_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_voice_settings",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("voice", sa.String(128), nullable=False, server_default="alba"),
        sa.Column("speed", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("pitch", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("volume", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("cloned_voice_id", sa.String(255), nullable=True),
        sa.Column("cloned_voice_name", sa.String(255), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("deepspace_voice_settings")
