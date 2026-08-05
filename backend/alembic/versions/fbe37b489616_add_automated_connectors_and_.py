"""Add automated connectors and integrations models

Revision ID: fbe37b489616
Revises: 20260425_0027
Create Date: 2026-05-03 07:57:05.915100
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "fbe37b489616"
down_revision = "20260425_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "ui_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "connectors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("collection_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sync_frequency",
            sa.String(length=32),
            server_default=sa.text("'daily'"),
            nullable=False,
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("error_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["document_collections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connectors_collection_id"),
        "connectors",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connectors_integration_id"),
        "connectors",
        ["integration_id"],
        unique=False,
    )
    op.create_index(op.f("ix_connectors_tenant_id"), "connectors", ["tenant_id"], unique=False)

    op.create_table(
        "connector_secrets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("connector_id", sa.UUID(), nullable=False),
        sa.Column("encrypted_data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_secrets_connector_id"),
        "connector_secrets",
        ["connector_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_secrets_tenant_id"),
        "connector_secrets",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_connector_secrets_tenant_id"), table_name="connector_secrets")
    op.drop_index(op.f("ix_connector_secrets_connector_id"), table_name="connector_secrets")
    op.drop_table("connector_secrets")
    op.drop_index(op.f("ix_connectors_tenant_id"), table_name="connectors")
    op.drop_index(op.f("ix_connectors_integration_id"), table_name="connectors")
    op.drop_index(op.f("ix_connectors_collection_id"), table_name="connectors")
    op.drop_table("connectors")
    op.drop_table("integrations")
