import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.integrations.models.connector import Connector, ConnectorStatus
from app.providers.models.provider_assignment import ProviderAssignment
from app.services.deepspace.subagents.subagent_registry import SubagentRegistry

logger = logging.getLogger(__name__)


class VitalsService:
    @staticmethod
    async def get_system_vitals(tenant_id: Any) -> dict[str, Any]:
        """
        Check core system vitals: Internet, LLM, Search, and Source connectivity.
        """
        settings = get_settings()
        factory = get_session_factory()
        db = factory()

        vitals = {
            "internet": "disconnected",
            "llm": "disconnected",
            "web_search": "unavailable",
            "sources": 0,
            "connector_statuses": {},
            "proactive_daemon": {
                "enabled": bool(
                    getattr(settings, "deepspace_proactive_daemon_enabled", False)
                ),
                "phase": "disabled",
                "timestamp": None,
                "interval_seconds": int(
                    getattr(
                        settings, "deepspace_proactive_daemon_interval_seconds", 300
                    )
                ),
                "healthy": False,
            },
        }

        try:
            # 1. Check Internet (Quick ping)
            async with httpx.AsyncClient(timeout=2.0) as client:
                try:
                    res = await client.get("https://www.google.com")
                    if res.status_code == 200:
                        vitals["internet"] = "connected"
                except Exception:
                    vitals["internet"] = "disconnected"

            # 2. Check LLM Connectivity
            stmt = select(ProviderAssignment).where(
                ProviderAssignment.tenant_id == tenant_id,
                ProviderAssignment.feature_scope == "chat",
            )
            assignment = db.execute(stmt).scalars().first()
            if assignment:
                vitals["llm"] = "connected"
            else:
                # Fallback: check if any provider config supports chat
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

            # 3. Check Web Search (Check if any search provider is assigned)
            stmt_search = select(ProviderAssignment).where(
                ProviderAssignment.tenant_id == tenant_id,
                ProviderAssignment.feature_scope == "web_search",
            )
            search_assignment = db.execute(stmt_search).scalars().first()
            if search_assignment:
                vitals["web_search"] = "available"
            else:
                # Fallback: check if any provider config is Tavily or Perplexity
                from app.providers.models.provider_config import ProviderConfig

                stmt_search_cfg = select(ProviderConfig).where(
                    ProviderConfig.tenant_id == tenant_id,
                    ProviderConfig.enabled,
                    ProviderConfig.provider_type.in_(
                        ["tavily", "perplexity", "google-search"]
                    ),
                )
                if db.execute(stmt_search_cfg).scalars().first():
                    vitals["web_search"] = "available"
                elif settings.llm_provider == "perplexity":
                    vitals["web_search"] = "available"

            # 4. Check Sources
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

            daemon = SubagentRegistry(settings).get_daemon_heartbeat()
            if daemon:
                timestamp_raw = str(daemon.get("timestamp") or "")
                healthy = False
                if timestamp_raw:
                    try:
                        timestamp = datetime.fromisoformat(
                            timestamp_raw.replace("Z", "+00:00")
                        )
                        interval_seconds_raw = daemon.get("interval_seconds")
                        interval_seconds = (
                            int(interval_seconds_raw)
                            if interval_seconds_raw is not None
                            else int(
                                getattr(
                                    settings,
                                    "deepspace_proactive_daemon_interval_seconds",
                                    300,
                                )
                            )
                        )
                        healthy = daemon.get("phase") != "error" and (
                            datetime.now(UTC) - timestamp
                        ).total_seconds() <= max(interval_seconds * 3, 300)
                    except Exception:  # noqa: BLE001
                        healthy = False
                daemon_interval_raw = daemon.get("interval_seconds")
                daemon_interval = (
                    int(daemon_interval_raw)
                    if daemon_interval_raw is not None
                    else int(
                        getattr(
                            settings, "deepspace_proactive_daemon_interval_seconds", 300
                        )
                    )
                )
                vitals["proactive_daemon"] = {
                    "enabled": bool(
                        getattr(settings, "deepspace_proactive_daemon_enabled", False)
                    ),
                    "phase": str(daemon.get("phase") or "running"),
                    "timestamp": daemon.get("timestamp"),
                    "interval_seconds": daemon_interval,
                    "healthy": healthy,
                }

        except Exception as e:
            logger.error(f"Vitals check failed: {e}")
        finally:
            db.close()

        return vitals
