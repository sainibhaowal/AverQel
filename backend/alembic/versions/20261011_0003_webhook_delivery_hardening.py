"""Harden webhook delivery reliability, idempotency, and diagnostics."""

import sqlalchemy as sa

from alembic import op

revision = "20261011_0003"
down_revision = "20261011_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_webhook_subscriptions",
        sa.Column("disabled_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_webhook_subscriptions",
        sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_webhook_deliveries",
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "document_webhook_deliveries",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_document_webhook_deliveries_next_attempt_at",
        "document_webhook_deliveries",
        ["next_attempt_at"],
    )
    # Existing best-effort delivery code could have emitted the same source
    # event more than once. Keep the oldest audit row before enforcing the
    # new idempotency key; NULL event IDs remain intentionally unrestricted.
    op.execute(sa.text("""
            DELETE FROM document_webhook_deliveries duplicate
            USING document_webhook_deliveries keeper
            WHERE duplicate.event_id IS NOT NULL
              AND duplicate.tenant_id = keeper.tenant_id
              AND duplicate.subscription_id = keeper.subscription_id
              AND duplicate.event_id = keeper.event_id
              AND (
                duplicate.created_at > keeper.created_at
                OR (duplicate.created_at = keeper.created_at AND duplicate.id > keeper.id)
              )
            """))
    op.create_unique_constraint(
        "uq_document_webhook_delivery_event",
        "document_webhook_deliveries",
        ["tenant_id", "subscription_id", "event_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_document_webhook_delivery_event",
        "document_webhook_deliveries",
        type_="unique",
    )
    op.drop_index(
        "ix_document_webhook_deliveries_next_attempt_at", table_name="document_webhook_deliveries"
    )
    op.drop_column("document_webhook_deliveries", "next_attempt_at")
    op.drop_column("document_webhook_deliveries", "payload")
    op.drop_column("document_webhook_subscriptions", "secret_rotated_at")
    op.drop_column("document_webhook_subscriptions", "disabled_reason")
