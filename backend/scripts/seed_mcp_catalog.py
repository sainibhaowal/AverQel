"""Idempotently seed AverQel's reviewed official remote MCP catalog."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.integrations.services.mcp_catalog_service import MCPCatalogService
from app.platform.database.session import get_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_mcp_catalog() -> dict[str, int]:
    """Persist only public, code-reviewed marketplace metadata."""
    with get_session_factory()() as session:
        result = MCPCatalogService(session).sync_official_providers()
        session.commit()
    payload = result.as_dict()
    logger.info("Curated MCP catalog synchronization complete: %s", payload)
    return payload


if __name__ == "__main__":
    seed_mcp_catalog()
