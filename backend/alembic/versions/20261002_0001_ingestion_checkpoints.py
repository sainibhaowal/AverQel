"""Persist ingestion checkpoints for durable embedding recovery."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261002_0001"
down_revision = "20261001_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs", sa.Column("checkpoint_stage", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("checkpoint_cursor", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("checkpoint_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("ingestion_jobs", sa.Column("pause_reason", sa.String(length=128), nullable=True))
    op.add_column(
        "ingestion_jobs",
        sa.Column("resume_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("ingestion_jobs", "resume_count")
    op.drop_column("ingestion_jobs", "pause_reason")
    op.drop_column("ingestion_jobs", "checkpoint_updated_at")
    op.drop_column("ingestion_jobs", "checkpoint_cursor")
    op.drop_column("ingestion_jobs", "checkpoint_stage")
