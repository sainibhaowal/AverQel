from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context
from app import models  # noqa: F401
from app.db.base import Base

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
        compare_type=True,
        compare_server_default=True,
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
            compare_type=True,
            compare_server_default=True,
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
