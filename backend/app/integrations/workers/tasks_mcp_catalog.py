"""Background synchronization for AverQel's curated MCP provider catalog."""

from __future__ import annotations

import logging

from app.integrations.services.mcp_catalog_service import MCPCatalogService
from app.platform.database.session import SessionLocal
from app.platform.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="mcp.sync_official_catalog")
def sync_official_mcp_catalog() -> dict[str, int]:
    """Idempotently apply reviewed catalog metadata without contacting vendors."""
    with SessionLocal() as session:
        try:
            result = MCPCatalogService(session).sync_official_providers()
            session.commit()
            return result.as_dict()
        except Exception:
            session.rollback()
            logger.exception("Curated MCP catalog synchronization failed")
            raise
