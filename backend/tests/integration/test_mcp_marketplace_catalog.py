from __future__ import annotations

from sqlalchemy import delete

from app.integrations.catalog.mcp_official_providers import CURATED_MCP_CATALOG_SOURCE
from app.integrations.models.mcp_server import MCPRegistryEntry
from tests.integration import test_mcp_catalog_service as catalog_tests


def _clean(session) -> None:
    session.execute(
        delete(MCPRegistryEntry).where(
            MCPRegistryEntry.source.in_((CURATED_MCP_CATALOG_SOURCE, "external-test-catalog"))
        )
    )
    session.commit()


def test_marketplace_catalog_seeds_all_reviewed_providers(db_session) -> None:
    _clean(db_session)
    catalog_tests.test_sync_official_mcp_catalog_creates_six_safe_entries(db_session)


def test_marketplace_catalog_sync_is_idempotent_and_source_scoped(db_session) -> None:
    _clean(db_session)
    catalog_tests.test_sync_official_mcp_catalog_is_idempotent_and_preserves_other_sources(
        db_session
    )
