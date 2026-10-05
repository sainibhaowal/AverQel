"""Add feedback/support conversations and durable user notifications.

Revision ID: 20261012_0010
Revises: 20261012_0009
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0010"
down_revision = "20261012_0009"
branch_labels = None
depends_on = None


def _enable_tenant_rls(table_name: str, policy_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {policy_name} ON {table_name}
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
            "priority", sa.String(length=16), server_default=sa.text("'normal'"), nullable=False
        ),
    )
    op.add_column(
        "app_feedback",
        sa.Column("status", sa.String(length=32), server_default=sa.text("'new'"), nullable=False),
    )
    op.add_column(
        "app_feedback",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_app_feedback_status", "app_feedback", ["status"], unique=False)

    op.create_table(
        "support_ticket_messages",
        sa.Column(
            "id",
            uuid,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
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
            "author_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "author_role", sa.String(length=24), server_default=sa.text("'user'"), nullable=False
        ),
        sa.Column(
            "kind", sa.String(length=32), server_default=sa.text("'message'"), nullable=False
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_support_ticket_messages_tenant_id", "support_ticket_messages", ["tenant_id"]
    )
    op.create_index(
        "ix_support_ticket_messages_ticket_id", "support_ticket_messages", ["ticket_id"]
    )
    op.create_index(
        "ix_support_ticket_messages_author_user_id", "support_ticket_messages", ["author_user_id"]
    )
    op.create_index(
        "ix_support_ticket_messages_ticket_created",
        "support_ticket_messages",
        ["ticket_id", "created_at"],
    )
    _enable_tenant_rls("support_ticket_messages", "tenant_isolation_support_ticket_messages")

    op.create_table(
        "app_feedback_messages",
        sa.Column(
            "id",
            uuid,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "feedback_id",
            uuid,
            sa.ForeignKey("app_feedback.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "author_role", sa.String(length=24), server_default=sa.text("'user'"), nullable=False
        ),
        sa.Column(
            "kind", sa.String(length=32), server_default=sa.text("'message'"), nullable=False
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_app_feedback_messages_tenant_id", "app_feedback_messages", ["tenant_id"])
    op.create_index(
        "ix_app_feedback_messages_feedback_id", "app_feedback_messages", ["feedback_id"]
    )
    op.create_index(
        "ix_app_feedback_messages_author_user_id", "app_feedback_messages", ["author_user_id"]
    )
    op.create_index(
        "ix_app_feedback_messages_feedback_created",
        "app_feedback_messages",
        ["feedback_id", "created_at"],
    )
    _enable_tenant_rls("app_feedback_messages", "tenant_isolation_app_feedback_messages")

    op.create_table(
        "user_notifications",
        sa.Column(
            "id",
            uuid,
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "recipient_user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_domain", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("href", sa.String(length=512), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "recipient_user_id", "idempotency_key", name="uq_user_notification_recipient_dedupe"
        ),
    )
    op.create_index("ix_user_notifications_tenant_id", "user_notifications", ["tenant_id"])
    op.create_index(
        "ix_user_notifications_recipient_user_id", "user_notifications", ["recipient_user_id"]
    )
    op.create_index("ix_user_notifications_event_domain", "user_notifications", ["event_domain"])
    op.create_index(
        "ix_user_notifications_recipient_created",
        "user_notifications",
        ["recipient_user_id", "created_at"],
    )
    _enable_tenant_rls("user_notifications", "tenant_isolation_user_notifications")


def downgrade() -> None:
    for table, policy in (
        ("user_notifications", "tenant_isolation_user_notifications"),
        ("app_feedback_messages", "tenant_isolation_app_feedback_messages"),
        ("support_ticket_messages", "tenant_isolation_support_ticket_messages"),
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("user_notifications")
    op.drop_table("app_feedback_messages")
    op.drop_table("support_ticket_messages")
    op.drop_index("ix_app_feedback_status", table_name="app_feedback")
    op.drop_column("app_feedback", "updated_at")
    op.drop_column("app_feedback", "status")
    op.drop_column("support_tickets", "priority")
