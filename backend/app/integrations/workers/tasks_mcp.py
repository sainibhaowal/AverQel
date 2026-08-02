"""Background MCP lifecycle and catalog refresh jobs."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import anyio
from sqlalchemy import select, text

from app.core.config import get_settings
from app.integrations.models.mcp_server import MCPServer
from app.integrations.repositories.mcp_events import MCPEventsRepository
from app.integrations.services.mcp_runtime import (
    MCPCatalog,
    build_mcp_server_runtime,
    mcp_server_provider_available,
)
from app.platform.database.session import SessionLocal, set_db_tenant_context
from app.platform.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _load_catalog(runtime: object) -> dict[str, object]:
    """Load required tools and best-effort optional MCP catalog surfaces.

    MCP servers are allowed to omit prompts, resources, or resource templates.
    A server returning "method not found" for one of those optional methods
    must not discard a successfully discovered tool catalog.
    """
    tools = await runtime.list_tools()  # type: ignore[attr-defined]

    async def optional(name: str) -> list[object]:
        loader = getattr(runtime, name)
        try:
            return await loader()
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "MCP server does not support optional catalog method %s: %s",
                name,
                type(exc).__name__,
            )
            return []

    return {
        "tools": tools,
        "prompts": await optional("list_prompts"),
        "resources": await optional("list_resources"),
        "resource_templates": await optional("list_resource_templates"),
    }


@celery_app.task(name="mcp.refresh_server_catalog")
def refresh_server_catalog(server_id: str, tenant_id: str) -> dict[str, object]:
    """Refresh tools/prompts/resources and append a durable catalog event."""
    with SessionLocal() as db:
        tenant_uuid = uuid.UUID(tenant_id)
        set_db_tenant_context(db, tenant_uuid)
        locked = db.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"mcp-catalog:{server_id}"},
        ).scalar()
        if not locked:
            return {"status": "already_running", "server_id": server_id}
        server = db.execute(
            select(MCPServer).where(MCPServer.id == uuid.UUID(server_id), MCPServer.tenant_id == tenant_uuid)
        ).scalar_one_or_none()
        if server is None:
            return {"status": "not_found"}
        provider_available, _provider_reason = mcp_server_provider_available(db, server)
        if not provider_available:
            server.status = "failed"
            server.last_error = "MCP provider is disabled"
            db.commit()
            return {"status": "provider_disabled", "server_id": server_id}
        async def _notification(method: str, params: object) -> None:
            if method.endswith("tools/list_changed") or method.endswith("prompts/list_changed") or method.endswith("resources/list_changed"):
                MCPEventsRepository(db).append(
                    tenant_id=tenant_uuid,
                    server_id=server.id,
                    event_type=method.replace("/", "_"),
                    payload={"params": params if isinstance(params, dict) else {}},
                    user_id=server.user_id,
                )

        runtime = build_mcp_server_runtime(db=db, settings=get_settings(), server=server, notification_handler=_notification)
        if runtime is None:
            server.status = "failed"
            server.last_error = "MCP runtime unavailable"
            db.commit()
            return {"status": "failed", "error": server.last_error}

        try:
            catalog = anyio.run(_load_catalog, runtime)
            catalog["tools"] = [
                {**item, "inputSchema": MCPCatalog.normalize_schema(item.get("inputSchema"))}
                for item in catalog["tools"] if isinstance(item, dict)
            ]
            catalog_revision = int(server.catalog_revision or 0) + 1
            server.config = {
                **server.config,
                "mcp_tools_cache": catalog["tools"],
                "mcp_prompts_cache": catalog["prompts"],
                "mcp_resources_cache": catalog["resources"],
                "mcp_resource_templates_cache": catalog["resource_templates"],
                "mcp_catalog_tool_count": len(catalog["tools"]),
                "mcp_catalog_last_sync_at": datetime.now(UTC).isoformat(),
                "catalog_revision": catalog_revision,
            }
            server.catalog_revision = catalog_revision
            server.status = "connected"
            server.last_error = None
            server.reconnect_attempts = 0
            server.last_connected_at = datetime.now(UTC)
            MCPEventsRepository(db).append(
                tenant_id=tenant_uuid,
                server_id=server.id,
                event_type="catalog_refreshed",
                payload=catalog,
                user_id=server.user_id,
            )
            db.commit()
            return {"status": "connected", "counts": {key: len(value) for key, value in catalog.items()}}
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("MCP catalog refresh failed for %s", server.id)
            server.status = "failed"
            server.last_error = f"{type(exc).__name__}: MCP catalog refresh failed"
            server.reconnect_attempts = int(server.reconnect_attempts or 0) + 1
            MCPEventsRepository(db).append(
                tenant_id=tenant_uuid,
                server_id=server.id,
                event_type="connection_failed",
                payload={"error": str(exc)},
                user_id=server.user_id,
            )
            db.commit()
            raise


@celery_app.task(name="mcp.refresh_enabled_servers")
def refresh_enabled_servers() -> dict[str, int]:
    with SessionLocal() as db:
        # The scheduler is the trusted coordinator; child tasks re-enter the
        # tenant context before touching tenant-owned records.
        db.execute(text("SELECT set_config('app.tenant_id', 'bypass', true)"))
        servers = db.execute(select(MCPServer).where(MCPServer.enabled.is_(True))).scalars().all()
        for server in servers:
            monitor_server_lifecycle.delay(str(server.id), str(server.tenant_id))
        return {"scheduled": len(servers)}


@celery_app.task(bind=True, name="mcp.monitor_server_lifecycle", max_retries=100)
def monitor_server_lifecycle(self: object, server_id: str, tenant_id: str) -> dict[str, object]:
    """Keep one MCP session alive long enough to receive server notifications.

    Beat starts this task repeatedly, so a worker restart naturally resumes the
    lifecycle. The short lease avoids orphaned sessions while still providing
    continuous notification coverage between refresh ticks.
    """
    with SessionLocal() as db:
        tenant_uuid = uuid.UUID(tenant_id)
        set_db_tenant_context(db, tenant_uuid)
        server = db.execute(select(MCPServer).where(MCPServer.id == uuid.UUID(server_id), MCPServer.tenant_id == tenant_uuid)).scalar_one_or_none()
        if server is None or not server.enabled:
            return {"status": "stopped"}
        provider_available, _provider_reason = mcp_server_provider_available(db, server)
        if not provider_available:
            server.status = "failed"
            server.last_error = "MCP provider is disabled"
            db.commit()
            return {"status": "provider_disabled"}

        async def _notification(method: str, params: object) -> None:
            if method.endswith(("tools/list_changed", "prompts/list_changed", "resources/list_changed")):
                MCPEventsRepository(db).append(
                    tenant_id=tenant_uuid, server_id=server.id,
                    event_type=method.replace("/", "_"),
                    payload={"params": params if isinstance(params, dict) else {}}, user_id=server.user_id,
                )
                db.commit()
                refresh_server_catalog.delay(str(server.id), str(server.tenant_id))

        try:
            runtime = build_mcp_server_runtime(db=db, settings=get_settings(), server=server, notification_handler=_notification)
            if runtime is None:
                server.status = "needs_auth"
                db.commit()
                return {"status": "needs_auth"}

            # Runtime construction reads encrypted OAuth metadata.  End that
            # transaction before keeping the remote MCP session open for its
            # 110-second notification lease; otherwise an idle worker session
            # can retain DB resources and eventually starve ordinary UI reads.
            db.commit()

            async def _hold() -> None:
                async with runtime.session():
                    await anyio.sleep(110)

            anyio.run(_hold)
            server.status = "connected"
            server.last_error = None
            server.reconnect_attempts = 0
            db.commit()
            return {"status": "connected"}
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            server.status = "failed"
            server.last_error = str(exc)[:1000]
            server.reconnect_attempts = int(server.reconnect_attempts or 0) + 1
            MCPEventsRepository(db).append(
                tenant_id=tenant_uuid, server_id=server.id,
                event_type="lifecycle_failed", payload={"error": str(exc)}, user_id=server.user_id,
            )
            db.commit()
            logger.exception("MCP lifecycle failed for %s", server.id)
            # Celery retries provide durable reconnect/backoff across worker
            # crashes. The attempt is persisted above before rescheduling.
            retry = getattr(self, "retry", None)
            if callable(retry):
                backoff = min(300, 2 ** min(int(server.reconnect_attempts or 1), 8))
                raise retry(exc=exc, countdown=backoff) from exc
            return {"status": "failed", "error": str(exc)}
