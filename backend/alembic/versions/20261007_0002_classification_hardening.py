"""Add durable classification run and application history."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261007_0002"
# The repository already had a later webhook-history head on the parallel
# organization branch. This migration is the additive merge point so deploys
# do not leave two competing heads.
down_revision = ("20261007_0001", "20261011_0001")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_classification_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=24), server_default="manual", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
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
            ["rule_id"], ["document_classification_rules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_classification_runs_tenant_id", "document_classification_runs", ["tenant_id"]
    )
    op.create_index(
        "ix_document_classification_runs_rule_id", "document_classification_runs", ["rule_id"]
    )
    op.create_index(
        "ix_document_classification_runs_actor_user_id",
        "document_classification_runs",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_document_classification_runs_status", "document_classification_runs", ["status"]
    )

    op.create_table(
        "document_classification_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=24), server_default="upload", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="matched", nullable=False),
        sa.Column(
            "actions", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["document_classification_rules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["document_classification_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_classification_applications_tenant_id",
        "document_classification_applications",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_classification_applications_rule_id",
        "document_classification_applications",
        ["rule_id"],
    )
    op.create_index(
        "ix_document_classification_applications_run_id",
        "document_classification_applications",
        ["run_id"],
    )
    op.create_index(
        "ix_document_classification_applications_document_id",
        "document_classification_applications",
        ["document_id"],
    )
    op.create_index(
        "ix_document_classification_applications_created_at",
        "document_classification_applications",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_table("document_classification_applications")
    op.drop_table("document_classification_runs")
