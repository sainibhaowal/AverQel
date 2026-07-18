"""add_chat_message_reactions

Revision ID: 8b3a7c6e4d2a
Revises: 6e330a120cb9
Create Date: 2026-07-06 18:35:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8b3a7c6e4d2a'
down_revision = '6e330a120cb9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('collection_chat_messages', sa.Column('reactions', sa.String(length=1024), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('collection_chat_messages', 'reactions')
