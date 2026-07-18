from __future__ import annotations

from app.models.providers.provider_assignment import ProviderAssignment
from app.models.providers.provider_config import ProviderConfig
from app.models.providers.provider_health_check import ProviderHealthCheck
from app.models.providers.provider_model_cache import ProviderModelCache
from app.models.providers.provider_secret import ProviderSecret
from app.models.providers.provider_usage_record import ProviderUsageRecord


def test_provider_secret_schema_has_no_plaintext_column() -> None:
    columns = set(ProviderSecret.__table__.c.keys())
    assert "secret_ciphertext" in columns
    assert "secret_nonce" in columns
    assert "secret_kid" in columns
    assert "secret_value" not in columns
    assert "api_key" not in columns


def test_provider_config_workspace_scope_is_nullable() -> None:
    assert ProviderConfig.__table__.c.workspace_id.nullable is True
    assert ProviderAssignment.__table__.c.workspace_id.nullable is True


def test_provider_domain_tables_are_registered() -> None:
    assert ProviderConfig.__tablename__ == "provider_configs"
    assert ProviderSecret.__tablename__ == "provider_secrets"
    assert ProviderModelCache.__tablename__ == "provider_model_cache"
    assert ProviderAssignment.__tablename__ == "provider_assignments"
    assert ProviderHealthCheck.__tablename__ == "provider_health_checks"
    assert ProviderUsageRecord.__tablename__ == "provider_usage_records"
