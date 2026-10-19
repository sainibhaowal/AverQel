"""Allow anonymous platform-level authentication audit events.

Revision ID: 20261018_0002
Revises: 20261018_0001
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261018_0002"
down_revision = "20261018_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    # Platform-level events have no tenant owner and cannot be represented by the
    # previous schema. Remove them before restoring the NOT NULL constraint.
    op.execute("DELETE FROM audit_logs WHERE tenant_id IS NULL")
    op.alter_column(
        "audit_logs",
        "tenant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
