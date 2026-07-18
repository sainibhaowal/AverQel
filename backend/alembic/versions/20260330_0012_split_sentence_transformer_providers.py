"""split managed sentence-transformers providers

Revision ID: 20260330_0012
Revises: 20260329_0011
Create Date: 2026-03-30 09:15:00
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "20260330_0012"
down_revision = "20260329_0011"
branch_labels = None
depends_on = None


provider_configs = sa.table(
    "provider_configs",
    sa.column("id", sa.UUID()),
    sa.column("tenant_id", sa.UUID()),
    sa.column("workspace_id", sa.UUID()),
    sa.column("provider_type", sa.String()),
    sa.column("display_name", sa.String()),
    sa.column("api_base_url", sa.String()),
    sa.column("auth_mode", sa.String()),
    sa.column("enabled", sa.Boolean()),
    sa.column("is_local", sa.Boolean()),
    sa.column("supports_chat", sa.Boolean()),
    sa.column("supports_embeddings", sa.Boolean()),
    sa.column("supports_reranking", sa.Boolean()),
    sa.column("supports_model_listing", sa.Boolean()),
    sa.column("supports_model_install", sa.Boolean()),
    sa.column("default_chat_model", sa.String()),
    sa.column("default_embedding_model", sa.String()),
    sa.column("default_reranker_model", sa.String()),
    sa.column("timeout_seconds", sa.Integer()),
    sa.column("priority", sa.Integer()),
    sa.column("metadata_json", sa.JSON()),
)

provider_assignments = sa.table(
    "provider_assignments",
    sa.column("id", sa.UUID()),
    sa.column("tenant_id", sa.UUID()),
    sa.column("feature_scope", sa.String()),
    sa.column("provider_config_id", sa.UUID()),
    sa.column("model_name", sa.String()),
)

provider_model_cache = sa.table(
    "provider_model_cache",
    sa.column("id", sa.UUID()),
    sa.column("provider_config_id", sa.UUID()),
    sa.column("tenant_id", sa.UUID()),
    sa.column("model_name", sa.String()),
    sa.column("model_kind", sa.String()),
    sa.column("display_name", sa.String()),
    sa.column("context_window", sa.Integer()),
    sa.column("capabilities_json", sa.JSON()),
    sa.column("is_available", sa.Boolean()),
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(provider_configs).where(
            provider_configs.c.provider_type == "sentence-transformers",
            provider_configs.c.supports_embeddings.is_(True),
            provider_configs.c.supports_reranking.is_(True),
        )
    ).mappings()

    for row in rows:
        reranker_id = uuid.uuid4()
        bind.execute(
            provider_configs.update()
            .where(provider_configs.c.id == row["id"])
            .values(
                display_name="AverQel Server Embeddings",
                supports_embeddings=True,
                supports_reranking=False,
                default_reranker_model=None,
            )
        )
        bind.execute(
            provider_configs.insert().values(
                id=reranker_id,
                tenant_id=row["tenant_id"],
                workspace_id=row["workspace_id"],
                provider_type="sentence-transformers",
                display_name="AverQel Server ReRanker",
                api_base_url=row["api_base_url"],
                auth_mode=row["auth_mode"],
                enabled=row["enabled"],
                is_local=row["is_local"],
                supports_chat=False,
                supports_embeddings=False,
                supports_reranking=True,
                supports_model_listing=row["supports_model_listing"],
                supports_model_install=row["supports_model_install"],
                default_chat_model=None,
                default_embedding_model=None,
                default_reranker_model=row["default_reranker_model"]
                or "BAAI/bge-reranker-v2-m3",
                timeout_seconds=row["timeout_seconds"],
                priority=row["priority"],
                metadata_json=row["metadata_json"] or {},
            )
        )
        bind.execute(
            provider_assignments.update()
            .where(
                provider_assignments.c.provider_config_id == row["id"],
                provider_assignments.c.feature_scope.in_(
                    ["reranking", "fallback_reranking"]
                ),
            )
            .values(
                provider_config_id=reranker_id,
                model_name=sa.case(
                    (
                        provider_assignments.c.model_name.is_(None),
                        row["default_reranker_model"] or "BAAI/bge-reranker-v2-m3",
                    ),
                    else_=provider_assignments.c.model_name,
                ),
            )
        )

        reranker_models = bind.execute(
            sa.select(provider_model_cache).where(
                provider_model_cache.c.provider_config_id == row["id"],
                provider_model_cache.c.model_kind == "reranker",
            )
        ).mappings()
        for model in reranker_models:
            bind.execute(
                provider_model_cache.insert().values(
                    id=uuid.uuid4(),
                    provider_config_id=reranker_id,
                    tenant_id=model["tenant_id"],
                    model_name=model["model_name"],
                    model_kind=model["model_kind"],
                    display_name=model["display_name"],
                    context_window=model["context_window"],
                    capabilities_json=model["capabilities_json"] or {},
                    is_available=model["is_available"],
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    reranker_rows = bind.execute(
        sa.select(provider_configs).where(
            provider_configs.c.provider_type == "sentence-transformers",
            provider_configs.c.display_name == "AverQel Server ReRanker",
            provider_configs.c.supports_embeddings.is_(False),
            provider_configs.c.supports_reranking.is_(True),
        )
    ).mappings()

    for reranker in reranker_rows:
        embeddings_row = (
            bind.execute(
                sa.select(provider_configs).where(
                    provider_configs.c.tenant_id == reranker["tenant_id"],
                    provider_configs.c.workspace_id.is_not_distinct_from(
                        reranker["workspace_id"]
                    ),
                    provider_configs.c.provider_type == "sentence-transformers",
                    provider_configs.c.display_name == "AverQel Server Embeddings",
                    provider_configs.c.supports_embeddings.is_(True),
                )
            )
            .mappings()
            .first()
        )
        if embeddings_row is None:
            continue
        bind.execute(
            provider_configs.update()
            .where(provider_configs.c.id == embeddings_row["id"])
            .values(
                supports_reranking=True,
                default_reranker_model=reranker["default_reranker_model"],
            )
        )
        bind.execute(
            provider_assignments.update()
            .where(
                provider_assignments.c.provider_config_id == reranker["id"],
                provider_assignments.c.feature_scope.in_(
                    ["reranking", "fallback_reranking"]
                ),
            )
            .values(provider_config_id=embeddings_row["id"])
        )
        bind.execute(
            provider_model_cache.delete().where(
                provider_model_cache.c.provider_config_id == reranker["id"]
            )
        )
        bind.execute(
            provider_configs.delete().where(provider_configs.c.id == reranker["id"])
        )
