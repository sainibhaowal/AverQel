from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from app.integrations.catalog.mcp_official_providers import (
    CURATED_MCP_CATALOG_SOURCE,
    OFFICIAL_MCP_PROVIDERS,
    validate_official_mcp_catalog,
)


@pytest.mark.unit_no_db
def test_official_mcp_catalog_contains_only_the_reviewed_remote_providers() -> None:
    assert [provider.provider_slug for provider in OFFICIAL_MCP_PROVIDERS] == [
        "google-gmail",
        "google-drive",
        "google-calendar",
        "google-chat",
        "google-people",
        "github",
        "notion",
        "slack",
    ]
    assert len({provider.remote_url for provider in OFFICIAL_MCP_PROVIDERS}) == 8
    assert len({provider.popularity_rank for provider in OFFICIAL_MCP_PROVIDERS}) == 8
    assert CURATED_MCP_CATALOG_SOURCE == "averqel-curated-official-v1"


@pytest.mark.unit_no_db
def test_official_mcp_catalog_is_public_metadata_without_credentials() -> None:
    validate_official_mcp_catalog()
    prohibited = (
        "secret",
        "token",
        "password",
        "authorization",
        "client_id",
        "client_secret",
    )

    for provider in OFFICIAL_MCP_PROVIDERS:
        values = provider.registry_values()
        endpoint = urlsplit(provider.remote_url)
        assert endpoint.scheme == "https"
        assert endpoint.hostname
        assert not endpoint.username
        assert not endpoint.password
        assert values["trust_status"] == "approved"
        if provider.provider_slug == "notion":
            assert values["catalog_status"] == "oauth_discovery_ready"
            assert values["raw_metadata"]["catalog"]["connection_ready"] is True
        else:
            assert values["catalog_status"] == "oauth_profile_required"
            assert values["raw_metadata"]["catalog"]["connection_ready"] is False
        assert values["logo_url"] is None
        assert values["package_metadata"]["tools"] == values["package_metadata"]["tool_preview"]
        assert (
            values["raw_metadata"]["catalog"]["tools"]
            == values["raw_metadata"]["catalog"]["tool_preview"]
        )
        assert all(
            forbidden not in key.lower()
            for key in values["raw_metadata"]["catalog"]
            for forbidden in prohibited
        )
