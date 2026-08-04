"""Persist detached DeepSpace SSE frames for reconnects.

Revision ID: 20260804_0002
Revises: 20260804_0001
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260804_0002"
down_revision = "20260804_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deepspace_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", sa.String(length=255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("frame", sa.Text(), nullable=False),
        sa.Column("event_name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "user_id", "conversation_id", "client_request_id"):
        op.create_index(f"ix_deepspace_run_events_{column}", "deepspace_run_events", [column])
    op.create_index(
        "uq_deepspace_run_events_request_sequence",
        "deepspace_run_events",
        ["tenant_id", "user_id", "conversation_id", "client_request_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("deepspace_run_events")
