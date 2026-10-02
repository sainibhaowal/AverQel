"""Grow chat message bodies to hold sealed envelopes.

A sealed envelope for max-length (4096-char) plaintext reaches ~5.6k chars
(base64 ciphertext plus headers), so the body column moves from
varchar(4096) to text. Plaintext input remains capped at 4096 chars by the
API schema; only sealed storage needs the headroom.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261012_0009"
down_revision = "20261012_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "collection_chat_messages",
        "message",
        existing_type=sa.String(length=4096),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "collection_chat_messages",
        "message",
        existing_type=sa.Text(),
        type_=sa.String(length=4096),
        existing_nullable=False,
    )
