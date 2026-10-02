"""Add advanced schedule configuration and durable schedule run history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261007_0003"
down_revision = "20261007_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_automation_schedules",
        sa.Column("cadence", sa.String(length=16), server_default="interval", nullable=False),
    )
    op.add_column(
        "document_automation_schedules",
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
    )
    op.add_column(
        "document_automation_schedules", sa.Column("run_time", sa.String(length=5), nullable=True)
    )
    op.add_column(
        "document_automation_schedules", sa.Column("weekday", sa.Integer(), nullable=True)
    )

    op.create_table(
        "document_automation_schedule_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["document_automation_schedules.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["document_classification_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "rule_id", name="uq_document_automation_schedule_rule"),
    )
    op.create_index(
        "ix_document_automation_schedule_rules_tenant_id",
        "document_automation_schedule_rules",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_automation_schedule_rules_schedule_id",
        "document_automation_schedule_rules",
        ["schedule_id"],
    )
    op.create_index(
        "ix_document_automation_schedule_rules_rule_id",
        "document_automation_schedule_rules",
        ["rule_id"],
    )

    op.create_table(
        "document_automation_schedule_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schedule_name", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=24), server_default="schedule", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("scanned_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("applied_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["document_automation_schedules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("tenant_id", "tenant_id"),
        ("schedule_id", "schedule_id"),
        ("actor_user_id", "actor_user_id"),
        ("status", "status"),
        ("created_at", "created_at"),
    ):
        op.create_index(
            f"ix_document_automation_schedule_runs_{name}",
            "document_automation_schedule_runs",
            [column],
        )


def downgrade() -> None:
    op.drop_table("document_automation_schedule_runs")
    op.drop_table("document_automation_schedule_rules")
    op.drop_column("document_automation_schedules", "weekday")
    op.drop_column("document_automation_schedules", "run_time")
    op.drop_column("document_automation_schedules", "timezone")
    op.drop_column("document_automation_schedules", "cadence")
