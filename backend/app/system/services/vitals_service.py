import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.integrations.models.connector import Connector, ConnectorStatus
from app.platform.database.session import get_session_factory
from app.providers.models.provider_assignment import ProviderAssignment

logger = logging.getLogger(__name__)


class VitalsService:
    @staticmethod
    async def get_system_vitals(tenant_id: Any) -> dict[str, Any]:
        """Check core system vitals without blocking unrelated API requests."""
        settings = get_settings()
        vitals: dict[str, Any] = {
            "internet": "disconnected",
            "llm": "disconnected",
            "web_search": "unavailable",
            "sources": 0,
            "connector_statuses": {},
        }

        try:
            # Network diagnostics already use an async client and a short timeout.
            async with httpx.AsyncClient(timeout=2.0) as client:
                try:
                    res = await client.get("https://www.google.com")
                    if res.status_code == 200:
                        vitals["internet"] = "connected"
                except Exception:  # noqa: BLE001
                    vitals["internet"] = "disconnected"

            # SQLAlchemy's synchronous Session is deliberately isolated from the
            # API event loop. A stalled pool/query cannot freeze other requests.
            database_vitals = await asyncio.wait_for(
                asyncio.to_thread(
                    VitalsService._collect_database_vitals,
                    tenant_id,
                    settings,
                ),
                timeout=4.0,
            )
            vitals.update(database_vitals)
        except TimeoutError:
            logger.warning("Vitals database check exceeded its 4 second budget")
        except Exception as exc:  # noqa: BLE001
            logger.error("Vitals check failed: %s", exc)

        return vitals

    @staticmethod
    def _collect_database_vitals(tenant_id: Any, settings: Any) -> dict[str, Any]:
        """Run synchronous diagnostic queries in a worker thread."""
        db = get_session_factory()()
        vitals: dict[str, Any] = {
            "llm": "disconnected",
            "web_search": "unavailable",
            "sources": 0,
            "connector_statuses": {},
        }

        try:
            # This local transaction setting only bounds diagnostic queries; it
            # does not change application transaction policy.
            db.execute(text("SET LOCAL statement_timeout = '3000ms'"))

            stmt = select(ProviderAssignment).where(
                ProviderAssignment.tenant_id == tenant_id,
                ProviderAssignment.feature_scope == "chat",
            )
            assignment = db.execute(stmt).scalars().first()
            if assignment:
                vitals["llm"] = "connected"
            else:
                from app.providers.models.provider_config import ProviderConfig

                stmt_cfg = select(ProviderConfig).where(
                    ProviderConfig.tenant_id == tenant_id,
                    ProviderConfig.enabled,
                    ProviderConfig.supports_chat,
                )
                if db.execute(stmt_cfg).scalars().first():
                    vitals["llm"] = "connected"
                elif settings.llm_provider != "disabled":
                    vitals["llm"] = "connected"

            stmt_search = select(ProviderAssignment).where(
                ProviderAssignment.tenant_id == tenant_id,
                ProviderAssignment.feature_scope == "web_search",
            )
            search_assignment = db.execute(stmt_search).scalars().first()
            if search_assignment:
                vitals["web_search"] = "available"
            else:
                from app.providers.models.provider_config import ProviderConfig

                stmt_search_cfg = select(ProviderConfig).where(
                    ProviderConfig.tenant_id == tenant_id,
                    ProviderConfig.enabled,
                    ProviderConfig.provider_type.in_(["tavily", "perplexity", "google-search"]),
                )
                if db.execute(stmt_search_cfg).scalars().first():
                    vitals["web_search"] = "available"
                elif settings.llm_provider == "perplexity":
                    vitals["web_search"] = "available"

            stmt_count = select(func.count(Connector.id)).where(
                Connector.tenant_id == tenant_id,
                Connector.status == ConnectorStatus.ACTIVE,
            )
            vitals["sources"] = db.execute(stmt_count).scalar() or 0

            status_stmt = (
                select(Connector.status, func.count(Connector.id))
                .where(Connector.tenant_id == tenant_id)
                .group_by(Connector.status)
            )
            vitals["connector_statuses"] = {
                str(status.value if hasattr(status, "value") else status): int(count)
                for status, count in db.execute(status_stmt)
            }

        except Exception as exc:  # noqa: BLE001
            logger.error("Vitals database check failed: %s", exc)
        finally:
            db.close()

        return vitals
