from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20261019_0004_composio_credentials_schema_repair.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "composio_credentials_schema_repair",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.db
def test_schema_repair_preserves_legacy_key_and_creates_isolated_table(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = db_session.connection()
    connection.exec_driver_sql("DROP TABLE composio_credentials")
    connection.exec_driver_sql("""
        CREATE TABLE composio_credentials (
            id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            secret_ciphertext BYTEA NOT NULL,
            secret_nonce BYTEA NOT NULL,
            secret_kid VARCHAR(128) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    connection.execute(
        text("""
            INSERT INTO composio_credentials (id, secret_ciphertext, secret_nonce, secret_kid)
            VALUES (1, :ciphertext, :nonce, :kid)
            """),
        {"ciphertext": b"legacy-encrypted-value", "nonce": b"legacy-nonce", "kid": "legacy"},
    )

    migration = _migration_module()
    operations = Operations(MigrationContext.configure(connection))
    monkeypatch.setattr(migration, "op", operations)
    migration.upgrade()

    inspector = inspect(connection)
    assert inspector.has_table("composio_credentials")
    assert inspector.has_table("composio_legacy_platform_credentials")
    assert {column["name"] for column in inspector.get_columns("composio_credentials")} == {
        "tenant_id",
        "user_id",
        "secret_ciphertext",
        "secret_nonce",
        "secret_kid",
        "updated_at",
    }
    legacy = connection.execute(text("""
            SELECT secret_ciphertext, secret_nonce, secret_kid
            FROM composio_legacy_platform_credentials
            WHERE id = 1
            """)).one()
    assert legacy == (b"legacy-encrypted-value", b"legacy-nonce", "legacy")
    rls = connection.execute(text("""
            SELECT relrowsecurity, relforcerowsecurity
            FROM pg_class
            WHERE oid = to_regclass('composio_credentials')
            """)).one()
    assert rls == (True, True)
