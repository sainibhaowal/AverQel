"""Add tenant-scoped dynamic Smart Collections."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261010_0001"
down_revision = "20261009_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_smart_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("match_mode", sa.String(length=8), server_default="all", nullable=False),
        sa.Column("conditions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_document_smart_collection_name"),
    )
    op.create_index(
        "ix_document_smart_collections_tenant_id", "document_smart_collections", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_table("document_smart_collections")
