from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from sqlalchemy import JSON, String, engine_from_config, pool
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import SchemaItem

from alembic import context
from alembic.runtime.migration import MigrationContext
from app.platform.database import model_registry  # noqa: F401
from app.platform.database.base import Base

# ============================================================
# Environment bootstrap
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=False)

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# These tables are retained by historical migrations for compatibility/data
# retention, but their ORM models were retired. Do not propose dropping them.
_LEGACY_UNMODELED_TABLES = {"agent_audit_logs", "agent_runtime_preferences"}


def _include_object(
    obj: SchemaItem,
    name: str | None,
    type_: Literal[
        "schema", "table", "column", "index", "unique_constraint", "foreign_key_constraint"
    ],
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    if not reflected:
        return True
    table_name = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    if type_ in {"index", "unique_constraint"}:
        # Indexes and uniqueness are owned by explicit migrations. This avoids
        # destructive autogeneration for historical names/definitions while the
        # reconciliation migration ensures current objects exist.
        return False
    return table_name not in _LEGACY_UNMODELED_TABLES


def _compare_type(
    context_: MigrationContext,
    inspected_column: Any,
    metadata_column: Any,
    inspected_type: Any,
    metadata_type: Any,
) -> bool | None:
    # JSON and JSONB are both valid PostgreSQL document storage. Historical
    # migrations use JSONB while several ORM models use the generic JSON type;
    # do not propose a risky table rewrite for this equivalent representation.
    if isinstance(inspected_type, JSON | JSONB) and isinstance(metadata_type, JSON | JSONB):
        return False
    if isinstance(inspected_type, String) and isinstance(metadata_type, SQLEnum):
        # The connector status was historically stored as VARCHAR. Keep that
        # compatible representation instead of forcing a live enum rewrite.
        return False
    return None


# ============================================================
# Database URL resolution
# ============================================================

database_url = os.getenv("AKS_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

resolved_url = config.get_main_option("sqlalchemy.url")
if not resolved_url or resolved_url == "driver://user:pass@localhost/dbname":
    raise RuntimeError(
        "Database URL is not configured. Set AKS_DATABASE_URL before running Alembic."
    )


# ============================================================
# Migration runners
# ============================================================


def run_migrations_offline() -> None:
    context.configure(
        url=resolved_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=_compare_type,
        include_object=_include_object,
        compare_server_default=False,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=_compare_type,
            include_object=_include_object,
            compare_server_default=False,
        )

        with context.begin_transaction():
            context.run_migrations()


# ============================================================
# Entrypoint
# ============================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
