"""Enforce feedback tenant RLS and index support retention scans.

Revision ID: 20261018_0003
Revises: 20261018_0002
"""

from __future__ import annotations

from alembic import op

revision = "20261018_0003"
down_revision = "20261018_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE app_feedback ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_feedback FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation_app_feedback ON app_feedback
        USING (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)
        WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
          OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)"""
    )
    op.create_index(
        "ix_app_feedback_terminal_retention",
        "app_feedback",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_support_tickets_terminal_retention",
        "support_tickets",
        ["status", "resolved_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_support_tickets_terminal_retention", table_name="support_tickets")
    op.drop_index("ix_app_feedback_terminal_retention", table_name="app_feedback")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_app_feedback ON app_feedback")
    op.execute("ALTER TABLE app_feedback NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app_feedback DISABLE ROW LEVEL SECURITY")
