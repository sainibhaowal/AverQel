from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.integrations.catalog.mcp_official_providers import CURATED_MCP_CATALOG_SOURCE
from app.integrations.models.mcp_server import MCPRegistryEntry
from app.integrations.services.mcp_catalog_service import MCPCatalogService


@pytest.fixture
def clean_curated_mcp_catalog(db_session: Session) -> Iterator[Session]:
    db_session.execute(
        delete(MCPRegistryEntry).where(
            MCPRegistryEntry.source.in_((CURATED_MCP_CATALOG_SOURCE, "external-test-catalog"))
        )
    )
    db_session.commit()
    try:
        yield db_session
    finally:
        db_session.execute(
            delete(MCPRegistryEntry).where(
                MCPRegistryEntry.source.in_((CURATED_MCP_CATALOG_SOURCE, "external-test-catalog"))
            )
        )
        db_session.commit()


def test_sync_official_mcp_catalog_creates_six_safe_entries(
    clean_curated_mcp_catalog: Session,
) -> None:
    result = MCPCatalogService(clean_curated_mcp_catalog).sync_official_providers()
    clean_curated_mcp_catalog.commit()

    rows = (
        clean_curated_mcp_catalog.execute(
            select(MCPRegistryEntry)
            .where(MCPRegistryEntry.source == CURATED_MCP_CATALOG_SOURCE)
            .order_by(MCPRegistryEntry.popularity_rank)
        )
        .scalars()
        .all()
    )

    assert result.as_dict() == {"created": 6, "updated": 0, "unchanged": 0, "total": 6}
    assert [row.server_name for row in rows] == [
        "google-gmail",
        "google-drive",
        "google-calendar",
        "google-chat",
        "google-people",
        "github",
    ]
    for row in rows:
        catalog = row.raw_metadata["catalog"]
        assert row.official is True
        assert row.verified is True
        assert row.trust_status == "approved"
        assert row.provider_slug == row.server_name
        assert row.publisher_type == "official"
        assert row.remote_url.startswith("https://")
        assert row.logo_url is None
        assert row.oauth_requirements["type"] == "oauth"
        assert row.requested_scopes == row.oauth_requirements["requested_scopes"]
        assert row.supported_products
        if row.tool_count:
            assert row.tool_categories
        assert row.catalog_badges["official"] is True
        assert row.trusted_logo_key
        assert row.health_status == "not_checked"
        assert catalog["connection_ready"] is False
        assert catalog["health"]["status"] == "not_checked"
        assert "client_secret" not in row.raw_metadata
        assert "access_token" not in row.raw_metadata


def test_sync_official_mcp_catalog_is_idempotent_and_preserves_other_sources(
    clean_curated_mcp_catalog: Session,
) -> None:
    session = clean_curated_mcp_catalog
    first_result = MCPCatalogService(session).sync_official_providers()
    session.commit()
    original_ids = {
        row.server_name: row.id
        for row in session.execute(
            select(MCPRegistryEntry).where(MCPRegistryEntry.source == CURATED_MCP_CATALOG_SOURCE)
        )
        .scalars()
        .all()
    }
    third_party = MCPRegistryEntry(
        source="external-test-catalog",
        server_name="google-gmail",
        display_name="External Google Gmail",
        provider_slug="external-google-gmail",
        publisher_type="community",
        transport="streamable_http",
        remote_url="https://example.com/mcp",
    )
    session.add(third_party)
    session.commit()

    second_result = MCPCatalogService(session).sync_official_providers()
    session.commit()
    current_ids = {
        row.server_name: row.id
        for row in session.execute(
            select(MCPRegistryEntry).where(MCPRegistryEntry.source == CURATED_MCP_CATALOG_SOURCE)
        )
        .scalars()
        .all()
    }

    assert first_result.created == 6
    assert second_result.as_dict() == {"created": 0, "updated": 0, "unchanged": 6, "total": 6}
    assert current_ids == original_ids
    assert session.get(MCPRegistryEntry, third_party.id) is not None
