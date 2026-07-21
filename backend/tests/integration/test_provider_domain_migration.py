from __future__ import annotations

from sqlalchemy import inspect

from app.platform.database.session import get_engine

EXPECTED_PROVIDER_TABLES = {
    "provider_configs",
    "provider_secrets",
    "provider_model_cache",
    "provider_assignments",
    "provider_health_checks",
    "provider_usage_records",
}


def test_provider_domain_tables_exist_after_migration() -> None:
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    assert EXPECTED_PROVIDER_TABLES.issubset(tables)
