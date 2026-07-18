"""add ingestion jobs tenant-document lookup index

Revision ID: 20260222_0007
Revises: 20260221_0006
Create Date: 2026-02-22 14:15:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260222_0007"
down_revision = "20260221_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ingestion_jobs_tenant_document",
        "ingestion_jobs",
        ["tenant_id", "document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_tenant_document", table_name="ingestion_jobs")
