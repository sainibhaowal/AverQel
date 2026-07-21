"""add_presence_and_e2e_fields

Revision ID: 6e330a120cb9
Revises: 42f3060e4bc3
Create Date: 2026-07-06 18:22:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '6e330a120cb9'
down_revision = '42f3060e4bc3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_presence table
    op.create_table('user_presence',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('is_online', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    
    # Add new columns to collection_chat_messages
    op.add_column('collection_chat_messages', sa.Column('status', sa.String(length=50), server_default='sent', nullable=False))
    op.add_column('collection_chat_messages', sa.Column('is_media', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('collection_chat_messages', sa.Column('media_mime_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    # Remove columns from collection_chat_messages
    op.drop_column('collection_chat_messages', 'media_mime_type')
    op.drop_column('collection_chat_messages', 'is_media')
    op.drop_column('collection_chat_messages', 'status')
    
    # Drop user_presence table
    op.drop_table('user_presence')
