"""add document extraction metadata columns

Revision ID: 20260302_0008
Revises: 20260222_0007
Create Date: 2026-03-02 17:10:00
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260302_0008"
down_revision = "20260222_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("extraction_method", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("extraction_coverage_score", sa.Float(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "extraction_ocr_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "extraction_vision_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "extraction_warnings",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "extraction_warnings")
    op.drop_column("documents", "extraction_vision_used")
    op.drop_column("documents", "extraction_ocr_used")
    op.drop_column("documents", "extraction_coverage_score")
    op.drop_column("documents", "extraction_method")
