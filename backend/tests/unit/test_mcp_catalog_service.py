from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.integrations.catalog.mcp_official_providers import validate_official_mcp_catalog
from app.integrations.services.mcp_catalog_service import MCPCatalogService


@pytest.mark.unit_no_db
def test_curated_catalog_validates_as_public_metadata() -> None:
    validate_official_mcp_catalog()


@pytest.mark.unit_no_db
def test_catalog_value_application_detects_secret_like_metadata_changes() -> None:
    entry = SimpleNamespace(name="old", trusted_logo_key="google", requested_scopes=[])
    changed = MCPCatalogService._apply_values(
        entry,
        {"name": "new", "trusted_logo_key": "google", "requested_scopes": ["scope.read"]},
    )

    assert changed is True
    assert entry.name == "new"
    assert entry.requested_scopes == ["scope.read"]
