"""Add device, moderation, and push-subscription security controls."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261012_0003"
down_revision = "20261012_0002"
branch_labels = None
depends_on = None


def _uuid(
    name: str, target: str, *, nullable: bool = False, ondelete: str = "CASCADE"
) -> sa.Column:
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
    )


def upgrade() -> None:
    op.add_column(
        "collection_chat_deliveries", sa.Column("device_id", sa.String(128), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE collection_chat_deliveries SET device_id = 'legacy' WHERE device_id IS NULL"
        )
    )
    op.alter_column(
        "collection_chat_deliveries",
        "device_id",
        nullable=False,
        server_default=sa.text("'legacy'"),
    )
    op.drop_constraint(
        "uq_collection_chat_delivery_recipient", "collection_chat_deliveries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_collection_chat_delivery_device",
        "collection_chat_deliveries",
        ["message_id", "user_id", "device_id"],
    )

    op.create_table(
        "collection_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        _uuid("tenant_id", "tenants.id"),
        _uuid("user_id", "users.id"),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("label", sa.String(128), server_default=sa.text("'Browser'"), nullable=False),
        sa.Column("identity_public_key", sa.Text(), nullable=True),
        sa.Column(
            "protocol_version",
            sa.String(32),
            server_default=sa.text("'legacy-shared-key'"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
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
        sa.UniqueConstraint(
            "tenant_id", "user_id", "device_id", name="uq_collection_device_identity"
        ),
    )
    for name, columns in {
        "ix_collection_devices_tenant_id": ["tenant_id"],
        "ix_collection_devices_user_id": ["user_id"],
        "ix_collection_devices_user_active": ["tenant_id", "user_id", "revoked_at"],
    }.items():
        op.create_index(name, "collection_devices", columns)

    op.create_table(
        "collection_chat_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        _uuid("tenant_id", "tenants.id"),
        _uuid("collection_id", "document_collections.id"),
        _uuid("blocker_user_id", "users.id"),
        _uuid("blocked_user_id", "users.id"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id", "blocker_user_id", "blocked_user_id", name="uq_collection_chat_block"
        ),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("collection_id", "collection_id"),
        ("blocker_user_id", "blocker_user_id"),
        ("blocked_user_id", "blocked_user_id"),
    ):
        op.create_index(f"ix_collection_chat_blocks_{name}", "collection_chat_blocks", [column])

    op.create_table(
        "collection_chat_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        _uuid("tenant_id", "tenants.id"),
        _uuid("collection_id", "document_collections.id"),
        _uuid("reporter_user_id", "users.id"),
        _uuid("reported_user_id", "users.id", nullable=True, ondelete="SET NULL"),
        _uuid("message_id", "collection_chat_messages.id", nullable=True, ondelete="SET NULL"),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default=sa.text("'open'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("collection_id", "collection_id"),
        ("reporter_user_id", "reporter_user_id"),
        ("reported_user_id", "reported_user_id"),
        ("message_id", "message_id"),
    ):
        op.create_index(f"ix_collection_chat_reports_{name}", "collection_chat_reports", [column])
    op.create_index(
        "ix_collection_chat_reports_collection_status",
        "collection_chat_reports",
        ["collection_id", "status", "created_at"],
    )

    op.create_table(
        "collection_push_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        _uuid("tenant_id", "tenants.id"),
        _uuid("user_id", "users.id"),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False),
        sa.Column("p256dh", sa.String(512), nullable=False),
        sa.Column("auth_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("auth_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("auth_kid", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        sa.UniqueConstraint("tenant_id", "user_id", "endpoint", name="uq_collection_push_endpoint"),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("user_id", "user_id"),
        ("device_id", "device_id"),
    ):
        op.create_index(
            f"ix_collection_push_subscriptions_{name}", "collection_push_subscriptions", [column]
        )


def downgrade() -> None:
    for name in (
        "ix_collection_push_subscriptions_device_id",
        "ix_collection_push_subscriptions_user_id",
        "ix_collection_push_subscriptions_tenant_id",
    ):
        op.drop_index(name, table_name="collection_push_subscriptions")
    op.drop_table("collection_push_subscriptions")
    op.drop_index(
        "ix_collection_chat_reports_collection_status", table_name="collection_chat_reports"
    )
    for name in (
        "message_id",
        "reported_user_id",
        "reporter_user_id",
        "collection_id",
        "tenant_id",
    ):
        op.drop_index(f"ix_collection_chat_reports_{name}", table_name="collection_chat_reports")
    op.drop_table("collection_chat_reports")
    for name in ("blocked_user_id", "blocker_user_id", "collection_id", "tenant_id"):
        op.drop_index(f"ix_collection_chat_blocks_{name}", table_name="collection_chat_blocks")
    op.drop_table("collection_chat_blocks")
    op.drop_index("ix_collection_devices_user_active", table_name="collection_devices")
    op.drop_index("ix_collection_devices_user_id", table_name="collection_devices")
    op.drop_index("ix_collection_devices_tenant_id", table_name="collection_devices")
    op.drop_table("collection_devices")
    op.drop_constraint(
        "uq_collection_chat_delivery_device", "collection_chat_deliveries", type_="unique"
    )
    op.create_unique_constraint(
        "uq_collection_chat_delivery_recipient",
        "collection_chat_deliveries",
        ["message_id", "user_id"],
    )
    op.drop_column("collection_chat_deliveries", "device_id")
