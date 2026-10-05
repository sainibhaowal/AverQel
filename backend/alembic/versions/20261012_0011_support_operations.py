"""Add support queue SLA fields and notification delivery preferences/outbox.

Revision ID: 20261012_0011
Revises: 20261012_0010
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0011"
down_revision = "20261012_0010"
branch_labels = None
depends_on = None


def _rls(table: str, policy: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {policy} ON {table}
      USING (current_setting('app.tenant_id', true) = 'bypass'
        OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)
      WITH CHECK (current_setting('app.tenant_id', true) = 'bypass'
        OR tenant_id = NULLIF(NULLIF(current_setting('app.tenant_id', true), ''), 'bypass')::uuid)"""
    )


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "support_tickets",
        sa.Column(
            "assigned_admin_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.add_column(
        "support_tickets",
        sa.Column("first_response_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "support_tickets", sa.Column("resolution_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "support_tickets", sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "support_tickets", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True)
    )
    for name, column in (
        ("ix_support_tickets_assigned_admin_id", "assigned_admin_id"),
        ("ix_support_tickets_first_response_due_at", "first_response_due_at"),
        ("ix_support_tickets_resolution_due_at", "resolution_due_at"),
    ):
        op.create_index(name, "support_tickets", [column])

    # Start the SLA clock for already-open tickets at rollout time. Backdating
    # deadlines to ticket creation would create an avoidable alert storm.
    op.execute("""
        UPDATE support_tickets
        SET first_response_due_at = COALESCE(first_response_due_at, CURRENT_TIMESTAMP +
            CASE priority
                WHEN 'urgent' THEN INTERVAL '1 hour'
                WHEN 'high' THEN INTERVAL '2 hours'
                WHEN 'low' THEN INTERVAL '24 hours'
                ELSE INTERVAL '8 hours'
            END),
            resolution_due_at = CASE
                WHEN status IN ('resolved', 'closed') THEN NULL
                ELSE COALESCE(resolution_due_at, CURRENT_TIMESTAMP +
                    CASE priority
                        WHEN 'urgent' THEN INTERVAL '8 hours'
                        WHEN 'high' THEN INTERVAL '24 hours'
                        WHEN 'low' THEN INTERVAL '168 hours'
                        ELSE INTERVAL '72 hours'
                    END)
            END
        WHERE first_response_due_at IS NULL OR resolution_due_at IS NULL
    """)

    op.create_table(
        "user_notification_preferences",
        sa.Column("id", uuid, primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "digest_frequency", sa.String(16), server_default=sa.text("'none'"), nullable=False
        ),
        sa.Column(
            "muted_domains",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_user_notification_preferences_owner"),
    )
    op.create_index(
        "ix_user_notification_preferences_tenant_id", "user_notification_preferences", ["tenant_id"]
    )
    op.create_index(
        "ix_user_notification_preferences_user_id", "user_notification_preferences", ["user_id"]
    )
    _rls("user_notification_preferences", "tenant_isolation_user_notification_preferences")

    op.create_table(
        "notification_deliveries",
        sa.Column("id", uuid, primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "notification_id",
            uuid,
            sa.ForeignKey("user_notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("channel", sa.String(16), server_default=sa.text("'email'"), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("notification_id", "channel", name="uq_notification_delivery_channel"),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("notification_id", "notification_id"),
        ("recipient_user_id", "recipient_user_id"),
        ("status", "status"),
    ):
        op.create_index(f"ix_notification_deliveries_{name}", "notification_deliveries", [column])
    op.create_index(
        "ix_notification_deliveries_pending",
        "notification_deliveries",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_notification_deliveries_leased_until", "notification_deliveries", ["leased_until"]
    )
    op.create_index(
        "ix_notification_deliveries_status_created",
        "notification_deliveries",
        ["status", "created_at"],
    )
    _rls("notification_deliveries", "tenant_isolation_notification_deliveries")

    op.create_table(
        "support_ticket_attachments",
        sa.Column("id", uuid, primary_key=True, nullable=False),
        sa.Column(
            "tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "ticket_id",
            uuid,
            sa.ForeignKey("support_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_bucket", sa.String(128), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    for col in ("tenant_id", "ticket_id", "uploaded_by_user_id"):
        op.create_index(f"ix_support_ticket_attachments_{col}", "support_ticket_attachments", [col])
    _rls("support_ticket_attachments", "tenant_isolation_support_ticket_attachments")
    op.create_index(
        "ix_user_notifications_dismissed_retention",
        "user_notifications",
        ["dismissed_at"],
        postgresql_where=sa.text("dismissed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_user_notifications_dismissed_retention", table_name="user_notifications")
    for table, policy in (
        ("support_ticket_attachments", "tenant_isolation_support_ticket_attachments"),
        ("notification_deliveries", "tenant_isolation_notification_deliveries"),
        ("user_notification_preferences", "tenant_isolation_user_notification_preferences"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
    for name in (
        "ix_support_tickets_assigned_admin_id",
        "ix_support_tickets_first_response_due_at",
        "ix_support_tickets_resolution_due_at",
    ):
        op.drop_index(name, table_name="support_tickets")
    for name in (
        "assigned_admin_id",
        "first_response_due_at",
        "resolution_due_at",
        "first_response_at",
        "resolved_at",
    ):
        op.drop_column("support_tickets", name)
