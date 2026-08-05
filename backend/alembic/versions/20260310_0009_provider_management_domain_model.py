"""create provider management domain model

Revision ID: 20260310_0009
Revises: 0f4d468f8713
Create Date: 2026-03-10 00:00:09
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260310_0009"
down_revision = "0f4d468f8713"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def _create_rls_policy(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY tenant_isolation_{table_name}
        ON {table_name}
        USING (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) = 'bypass'
            OR
            tenant_id = NULLIF(current_setting('app.tenant_id', true), 'bypass')::uuid
        )
        """)


def _drop_rls_policy(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table_name} ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "provider_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("api_base_url", sa.String(length=1024), nullable=True),
        sa.Column("auth_mode", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_local", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "supports_chat",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "supports_embeddings",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "supports_model_listing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "supports_model_install",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("default_chat_model", sa.String(length=255), nullable=True),
        sa.Column("default_embedding_model", sa.String(length=255), nullable=True),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "display_name",
            name="uq_provider_configs_tenant_workspace_name",
        ),
    )
    op.create_index("ix_provider_configs_tenant_id", "provider_configs", ["tenant_id"])
    op.create_index("ix_provider_configs_workspace_id", "provider_configs", ["workspace_id"])
    op.create_index("ix_provider_configs_provider_type", "provider_configs", ["provider_type"])
    op.create_index("ix_provider_configs_enabled", "provider_configs", ["enabled"])

    op.create_table(
        "provider_secrets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("secret_kid", sa.String(length=128), nullable=False),
        sa.Column("secret_type", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_rotated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["provider_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider_config_id",
            "secret_type",
            name="uq_provider_secrets_provider_secret_type",
        ),
    )
    op.create_index(
        "ix_provider_secrets_provider_config_id",
        "provider_secrets",
        ["provider_config_id"],
    )
    op.create_index("ix_provider_secrets_tenant_id", "provider_secrets", ["tenant_id"])

    op.create_table(
        "provider_model_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_kind", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column(
            "capabilities_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["provider_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "provider_config_id",
            "model_name",
            "model_kind",
            name="uq_provider_model_cache_provider_model_kind",
        ),
    )
    op.create_index(
        "ix_provider_model_cache_provider_config_id",
        "provider_model_cache",
        ["provider_config_id"],
    )
    op.create_index("ix_provider_model_cache_tenant_id", "provider_model_cache", ["tenant_id"])

    op.create_table(
        "provider_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feature_scope", sa.String(length=64), nullable=False),
        sa.Column("provider_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["provider_configs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "feature_scope",
            "priority",
            name="uq_provider_assignments_scope_priority",
        ),
    )
    op.create_index("ix_provider_assignments_tenant_id", "provider_assignments", ["tenant_id"])
    op.create_index(
        "ix_provider_assignments_workspace_id", "provider_assignments", ["workspace_id"]
    )
    op.create_index(
        "ix_provider_assignments_feature_scope",
        "provider_assignments",
        ["feature_scope"],
    )
    op.create_index(
        "ix_provider_assignments_provider_config_id",
        "provider_assignments",
        ["provider_config_id"],
    )

    op.create_table(
        "provider_health_checks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message_redacted", sa.String(length=512), nullable=True),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["provider_configs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_provider_health_checks_provider_config_id",
        "provider_health_checks",
        ["provider_config_id"],
    )
    op.create_index("ix_provider_health_checks_tenant_id", "provider_health_checks", ["tenant_id"])
    op.create_index("ix_provider_health_checks_status", "provider_health_checks", ["status"])
    op.create_index(
        "ix_provider_health_checks_checked_at", "provider_health_checks", ["checked_at"]
    )

    op.create_table(
        "provider_usage_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["provider_config_id"], ["provider_configs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_provider_usage_records_tenant_id", "provider_usage_records", ["tenant_id"])
    op.create_index(
        "ix_provider_usage_records_provider_config_id",
        "provider_usage_records",
        ["provider_config_id"],
    )
    op.create_index("ix_provider_usage_records_operation", "provider_usage_records", ["operation"])
    op.create_index(
        "ix_provider_usage_records_created_at", "provider_usage_records", ["created_at"]
    )

    for table_name in (
        "provider_configs",
        "provider_secrets",
        "provider_model_cache",
        "provider_assignments",
        "provider_health_checks",
        "provider_usage_records",
    ):
        _create_rls_policy(table_name)


def downgrade() -> None:
    for table_name in (
        "provider_usage_records",
        "provider_health_checks",
        "provider_assignments",
        "provider_model_cache",
        "provider_secrets",
        "provider_configs",
    ):
        _drop_rls_policy(table_name)

    op.drop_index("ix_provider_usage_records_created_at", table_name="provider_usage_records")
    op.drop_index("ix_provider_usage_records_operation", table_name="provider_usage_records")
    op.drop_index(
        "ix_provider_usage_records_provider_config_id",
        table_name="provider_usage_records",
    )
    op.drop_index("ix_provider_usage_records_tenant_id", table_name="provider_usage_records")
    op.drop_table("provider_usage_records")

    op.drop_index("ix_provider_health_checks_checked_at", table_name="provider_health_checks")
    op.drop_index("ix_provider_health_checks_status", table_name="provider_health_checks")
    op.drop_index("ix_provider_health_checks_tenant_id", table_name="provider_health_checks")
    op.drop_index(
        "ix_provider_health_checks_provider_config_id",
        table_name="provider_health_checks",
    )
    op.drop_table("provider_health_checks")

    op.drop_index("ix_provider_assignments_provider_config_id", table_name="provider_assignments")
    op.drop_index("ix_provider_assignments_feature_scope", table_name="provider_assignments")
    op.drop_index("ix_provider_assignments_workspace_id", table_name="provider_assignments")
    op.drop_index("ix_provider_assignments_tenant_id", table_name="provider_assignments")
    op.drop_table("provider_assignments")

    op.drop_index("ix_provider_model_cache_tenant_id", table_name="provider_model_cache")
    op.drop_index("ix_provider_model_cache_provider_config_id", table_name="provider_model_cache")
    op.drop_table("provider_model_cache")

    op.drop_index("ix_provider_secrets_tenant_id", table_name="provider_secrets")
    op.drop_index("ix_provider_secrets_provider_config_id", table_name="provider_secrets")
    op.drop_table("provider_secrets")

    op.drop_index("ix_provider_configs_enabled", table_name="provider_configs")
    op.drop_index("ix_provider_configs_provider_type", table_name="provider_configs")
    op.drop_index("ix_provider_configs_workspace_id", table_name="provider_configs")
    op.drop_index("ix_provider_configs_tenant_id", table_name="provider_configs")
    op.drop_table("provider_configs")
