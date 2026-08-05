"""Fix connector and secret schema discrepancies

Revision ID: 078c055efcaa
Revises: fbe37b489616
Create Date: 2026-05-03 08:33:47.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "078c055efcaa"
down_revision = "fbe37b489616"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fix connectors table
    op.add_column(
        "connectors",
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Fix connector_secrets table
    op.add_column(
        "connector_secrets",
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
    )
    op.add_column("connector_secrets", sa.Column("secret_nonce", sa.LargeBinary(), nullable=False))
    op.add_column(
        "connector_secrets",
        sa.Column("secret_kid", sa.String(length=128), nullable=False),
    )
    op.add_column(
        "connector_secrets",
        sa.Column("secret_type", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "connector_secrets",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "connector_secrets",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    # Remove old column
    op.drop_column("connector_secrets", "encrypted_data")

    # Add unique constraint to secrets
    op.create_unique_constraint(
        "uq_connector_secrets_connector_secret_type",
        "connector_secrets",
        ["connector_id", "secret_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_connector_secrets_connector_secret_type",
        "connector_secrets",
        type_="unique",
    )
    op.add_column(
        "connector_secrets",
        sa.Column("encrypted_data", sa.TEXT(), autoincrement=False, nullable=False),
    )
    op.drop_column("connector_secrets", "metadata_json")
    op.drop_column("connector_secrets", "expires_at")
    op.drop_column("connector_secrets", "secret_type")
    op.drop_column("connector_secrets", "secret_kid")
    op.drop_column("connector_secrets", "secret_nonce")
    op.drop_column("connector_secrets", "secret_ciphertext")
    op.drop_column("connectors", "next_sync_at")
