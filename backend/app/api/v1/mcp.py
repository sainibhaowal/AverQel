from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_auth_context
from app.core.rbac import require_permissions
from app.db.session import get_db, set_db_tenant_context
from app.models.integrations.mcp_server import MCPServer, MCPRegistryEntry
from app.worker.tasks_mcp import refresh_server_catalog
from app.services.integrations.mcp_oauth_service import MCPServerOAuthService
from app.core.config import get_settings
from app.services.integrations.mcp_endpoint_security import validate_remote_endpoint, MCPEndpointRejected

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _marketplace_capabilities(entry: MCPRegistryEntry) -> list[str]:
    package = entry.package_metadata if isinstance(entry.package_metadata, dict) else {}
    preview = package.get("tool_preview")
    if isinstance(preview, list):
        names = [str(item.get("name") or "").strip() for item in preview if isinstance(item, dict)]
        names = [name for name in names if name]
        if names:
            return names
    discovered = package.get("discovered_capabilities")
    if isinstance(discovered, list):
        values = [str(item).strip() for item in discovered if str(item).strip()]
        if values:
            return values
    raw_values: list[str] = []
    for key in ("tools", "capabilities", "features", "scopes"):
        value = package.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            raw_values.extend(str(item).strip() for item in value if str(item).strip())
    return sorted(dict.fromkeys(raw_values))


def _marketplace_tool_preview(entry: MCPRegistryEntry) -> list[dict[str, Any]]:
    package = entry.package_metadata if isinstance(entry.package_metadata, dict) else {}
    preview = package.get("tool_preview")
    if not isinstance(preview, list):
        return []
    return [item for item in preview if isinstance(item, dict) and str(item.get("name") or "").strip()]


def _marketplace_auth_type(entry: MCPRegistryEntry) -> str:
    requirements = entry.oauth_requirements if isinstance(entry.oauth_requirements, dict) else {}
    return str(requirements.get("type") or "setup_required")


def _marketplace_docs_url(entry: MCPRegistryEntry) -> str | None:
    raw = entry.raw_metadata if isinstance(entry.raw_metadata, dict) else {}
    server = raw.get("server") if isinstance(raw.get("server"), dict) else raw
    for key in ("documentationUrl", "documentation_url", "docsUrl", "docs_url", "documentation", "homepage"):
        value = server.get(key)
        if isinstance(value, str) and value.strip().startswith(("https://", "http://")):
            return value.strip()
    repository = server.get("repository")
    if isinstance(repository, dict):
        value = repository.get("url") or repository.get("web")
        if isinstance(value, str) and value.strip().startswith(("https://", "http://")):
            return value.strip()
    return None


def _marketplace_connection_options(entry: MCPRegistryEntry) -> list[dict[str, Any]]:
    """Expose registry-declared connection choices without vendor code."""
    raw = entry.raw_metadata if isinstance(entry.raw_metadata, dict) else {}
    server = raw.get("server") if isinstance(raw.get("server"), dict) else raw
    options: list[dict[str, Any]] = []
    for remote in server.get("remotes") or []:
        if not isinstance(remote, dict):
            continue
        url = remote.get("url") or remote.get("urlTemplate")
        options.append({
            "transport": remote.get("type") or "streamable_http",
            "url": url,
            "security_schemes": remote.get("securitySchemes") or {},
        })
    return options


class MCPServerRead(BaseModel):
    id: uuid.UUID
    name: str
    transport: str
    config: dict[str, Any]
    enabled: bool
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    last_error: str | None
    reconnect_attempts: int

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("config")
    def serialize_safe_config(self, value: dict[str, Any]) -> dict[str, Any]:
        """Never expose OAuth material or PKCE state to browser clients."""
        sensitive = {
            "access_token", "refresh_token", "token", "client_secret",
            "secret", "password", "authorization", "code", "code_verifier",
            "oauth_pending",
        }

        def redact(item: Any, key: str = "") -> Any:
            if key.lower() in sensitive or any(marker in key.lower() for marker in ("token", "secret", "verifier", "key")):
                return "[REDACTED]"
            if isinstance(item, dict):
                return {str(k): redact(v, str(k)) for k, v in item.items()}
            if isinstance(item, list):
                return [redact(v, key) for v in item]
            return item

        return redact(value) if isinstance(value, dict) else {}


class MCPCatalogReviewRequest(BaseModel):
    status: Literal["approved", "rejected", "discovered"]
    verification_source: str = Field(min_length=1, max_length=500)
    popularity_rank: int | None = Field(default=None, ge=1, le=1_000_000)


@router.get("/servers", response_model=list[MCPServerRead])
def list_servers(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    return list(session.execute(select(MCPServer).where(MCPServer.tenant_id == auth.tenant_id, MCPServer.user_id == auth.user_id).order_by(MCPServer.created_at.desc())).scalars().all())


@router.post("/marketplace/{entry_id}/connect", response_model=dict[str, Any], status_code=201)
def connect_marketplace_entry(
    entry_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    """Create a tenant connection only from a trusted marketplace entry."""
    set_db_tenant_context(session, auth.tenant_id)
    entry = session.get(MCPRegistryEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="MCP marketplace entry not found")
    if entry.trust_status != "approved":
        raise HTTPException(status_code=403, detail="Only official verified MCP entries can be connected")
    if not entry.remote_url:
        raise HTTPException(status_code=409, detail="This MCP entry does not publish a remote endpoint")
    try:
        endpoint = validate_remote_endpoint(entry.remote_url)
    except MCPEndpointRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    auth_type = _marketplace_auth_type(entry)
    if auth_type not in {"anonymous", "oauth"}:
        raise HTTPException(status_code=409, detail="This Google Workspace MCP entry is not ready for a supported connection")
    oauth_mode = "mcp_oauth" if auth_type == "oauth" else "none"
    config = {
        "server_url": endpoint,
        "oauth_mode": oauth_mode,
        "auth_type": auth_type,
        "registry_entry_id": str(entry.id),
        "source": entry.source,
        "categories": entry.categories or [],
    }
    server = MCPServer(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        name=entry.display_name,
        transport="streamable_http",
        config=config,
        enabled=True,
        status="needs_auth" if auth_type == "oauth" else "disconnected",
    )
    session.add(server)
    session.commit()
    session.refresh(server)
    result: dict[str, Any] = {"server": MCPServerRead.model_validate(server).model_dump(mode="json")}
    if oauth_mode == "none":
        refresh_server_catalog.delay(str(server.id), str(auth.tenant_id))
    else:
        try:
            result["authorization_url"] = MCPServerOAuthService(session, get_settings()).start(
                server=server,
                user_id=auth.user_id,
            )
        except Exception as exc:
            server.status = "needs_auth"
            server.last_error = str(exc)[:1000]
            session.commit()
            result["setup_required"] = True
    return result


@router.post("/servers/{server_id}/refresh", response_model=dict[str, Any])
def refresh_server(server_id: uuid.UUID, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    server = session.execute(select(MCPServer).where(MCPServer.id == server_id, MCPServer.tenant_id == auth.tenant_id, MCPServer.user_id == auth.user_id)).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    refresh_server_catalog.delay(str(server.id), str(auth.tenant_id))
    return {"status": "scheduled", "server_id": str(server.id)}


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def uninstall_server(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> Response:
    """Disconnect and permanently remove a tenant/user-owned MCP server."""
    set_db_tenant_context(session, auth.tenant_id)
    server = session.execute(
        select(MCPServer).where(
            MCPServer.id == server_id,
            MCPServer.tenant_id == auth.tenant_id,
            MCPServer.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    session.delete(server)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/servers/{server_id}/oauth/start", response_model=dict[str, str])
def start_oauth(server_id: uuid.UUID, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    server = session.execute(select(MCPServer).where(MCPServer.id == server_id, MCPServer.tenant_id == auth.tenant_id, MCPServer.user_id == auth.user_id)).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        url = MCPServerOAuthService(session, get_settings()).start(server=server, user_id=auth.user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"authorization_url": url}


@router.get("/servers/{server_id}/oauth/callback")
def oauth_callback(server_id: uuid.UUID, code: str, state: str, session: Session = Depends(get_db)):
    service = MCPServerOAuthService(session, get_settings())
    try:
        state_payload = service.verify_state(state)
        if state_payload.get("mcp_server_id") != str(server_id):
            raise ValueError("OAuth state does not belong to this MCP server")
        tenant_id = uuid.UUID(str(state_payload["tenant_id"]))
        set_db_tenant_context(session, tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    server = session.get(MCPServer, server_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        service.finish(server=server, code=code, state=state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    refresh_server_catalog.delay(str(server.id), str(server.tenant_id))
    origin = (get_settings().averqel_public_origin or "").strip().rstrip("/")
    if origin:
        query = urlencode({"mcp_status": "connected", "server_id": str(server.id)})
        return RedirectResponse(url=f"{origin}/dashboard/mcp?{query}", status_code=303)
    return {"status": "connected", "server_id": str(server.id)}


@router.get("/catalog", response_model=list[dict[str, Any]])
def catalog(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    """Return the synchronized registry catalog, never a hardcoded vendor list."""
    set_db_tenant_context(session, auth.tenant_id)
    rows = session.execute(select(MCPRegistryEntry).where(MCPRegistryEntry.remote_url.is_not(None), MCPRegistryEntry.trust_status == "approved").order_by(MCPRegistryEntry.display_name)).scalars().all()
    return [{"id": str(row.id), "name": row.display_name, "server_name": row.server_name,
             "publisher": row.publisher, "description": row.description, "transport": row.transport,
             "remote_url": row.remote_url, "categories": row.categories, "official": row.official,
             "verified": row.verified, "source": row.source, "oauth_requirements": row.oauth_requirements,
             "package_metadata": row.package_metadata, "logo_url": row.logo_url,
             "tool_count": row.tool_count, "last_catalog_sync_at": row.last_catalog_sync_at.isoformat() if row.last_catalog_sync_at else None,
             "docs_url": _marketplace_docs_url(row), "connection_options": _marketplace_connection_options(row),
             "capabilities": _marketplace_capabilities(row), "tool_preview": _marketplace_tool_preview(row),
             "catalog_status": row.catalog_status,
             "auth_type": _marketplace_auth_type(row), "trust_status": row.trust_status,
             "verification_source": row.verification_source, "popularity_rank": row.popularity_rank} for row in rows]

@router.get("/marketplace/facets", response_model=dict[str, Any])
def marketplace_facets(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    """Return filter values from catalog data, never from a vendor allowlist."""
    set_db_tenant_context(session, auth.tenant_id)
    rows = session.execute(select(MCPRegistryEntry).where(MCPRegistryEntry.remote_url.is_not(None), MCPRegistryEntry.trust_status == "approved")).scalars().all()
    categories = sorted({str(category) for row in rows for category in (row.categories or []) if str(category).strip()})
    transports = sorted({row.transport for row in rows if row.transport})
    auth_types = sorted({_marketplace_auth_type(row) for row in rows})
    trust_statuses = sorted({row.trust_status for row in rows if row.trust_status})
    return {"categories": categories, "transports": transports, "auth_types": auth_types, "trust_statuses": trust_statuses}


@router.get("/marketplace", response_model=dict[str, Any])
def marketplace(q: str | None = None, category: str | None = None, transport: str | None = None,
                official: bool | None = None, verified: bool | None = None,
                auth_type: str | None = None, trust_status: str | None = None,
                sort: Literal["default", "popular", "trending", "new", "alphabetical"] = "default",
                page: int = 1,
                page_size: int = 24, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    page, page_size = max(1, page), min(100, max(1, page_size))
    # Public users see only records approved by AverQel. Registry intake rows
    # remain internal until source, ownership, endpoint, and auth are checked.
    query = select(MCPRegistryEntry).where(MCPRegistryEntry.remote_url.is_not(None), MCPRegistryEntry.trust_status == "approved")
    if q: query = query.where(MCPRegistryEntry.display_name.ilike(f"%{q}%") | MCPRegistryEntry.description.ilike(f"%{q}%"))
    if transport: query = query.where(MCPRegistryEntry.transport == transport)
    if official is not None: query = query.where(MCPRegistryEntry.official.is_(official))
    if verified is not None: query = query.where(MCPRegistryEntry.verified.is_(verified))
    rows = session.execute(query.order_by(MCPRegistryEntry.display_name)).scalars().all()
    if category: rows = [r for r in rows if category.lower() in [str(x).lower() for x in (r.categories or [])]]
    if auth_type: rows = [r for r in rows if _marketplace_auth_type(r) == auth_type]
    if trust_status: rows = [r for r in rows if r.trust_status == trust_status]
    if sort == "alphabetical":
        rows.sort(key=lambda row: row.display_name.casefold())
    elif sort == "popular":
        rows.sort(key=lambda row: (row.popularity_rank is None, row.popularity_rank or 1_000_000, row.display_name.casefold()))
    elif sort in {"trending", "new"}:
        rows.sort(key=lambda row: (row.last_seen_at is None, row.last_seen_at), reverse=True)
    else:
        rows.sort(key=lambda row: (row.popularity_rank is None, row.popularity_rank or 1_000_000, row.display_name.casefold()))
    total = len(rows); rows = rows[(page - 1) * page_size: page * page_size]
    return {"items": [{"id": str(r.id), "name": r.display_name, "server_name": r.server_name, "publisher": r.publisher,
        "description": r.description, "transport": r.transport, "remote_url": r.remote_url,
        "categories": r.categories, "official": r.official, "verified": r.verified, "source": r.source,
        "oauth_requirements": r.oauth_requirements, "package_metadata": r.package_metadata,
        "action": "connect" if r.remote_url else "install",
        "logo_url": r.logo_url,
        "tool_count": r.tool_count, "last_catalog_sync_at": r.last_catalog_sync_at.isoformat() if r.last_catalog_sync_at else None,
        "verification_reason": r.verification_reason, "last_seen_at": r.last_seen_at.isoformat(),
        "docs_url": _marketplace_docs_url(r),
        "connection_options": _marketplace_connection_options(r),
        "capabilities": _marketplace_capabilities(r),
        "tool_preview": _marketplace_tool_preview(r),
        "catalog_status": r.catalog_status,
        "auth_type": _marketplace_auth_type(r), "trust_status": r.trust_status,
        "verification_source": r.verification_source, "popularity_rank": r.popularity_rank} for r in rows],
        "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}

@router.post("/catalog/{entry_id}/review", response_model=dict[str, Any])
def review_catalog_entry(
    entry_id: uuid.UUID,
    payload: MCPCatalogReviewRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permissions("mcp:catalog:manage")),
):
    """Approve only after AverQel has verified the vendor and endpoint."""
    set_db_tenant_context(session, auth.tenant_id)
    entry = session.get(MCPRegistryEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="MCP catalog entry not found")
    entry.trust_status = payload.status
    entry.verification_source = payload.verification_source
    entry.popularity_rank = payload.popularity_rank
    entry.verified_at = datetime.now(UTC) if payload.status == "approved" else None
    session.commit()
    return {"id": str(entry.id), "trust_status": entry.trust_status, "verification_source": entry.verification_source}


@router.get("/servers/{server_id}/inspector", response_model=dict[str, Any])
def inspector(server_id: uuid.UUID, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    from collections import Counter
    from app.models.integrations.mcp_server import MCPEvent, MCPOAuthToken
    set_db_tenant_context(session, auth.tenant_id)
    server = session.execute(select(MCPServer).where(MCPServer.id == server_id, MCPServer.tenant_id == auth.tenant_id, MCPServer.user_id == auth.user_id)).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    events = session.execute(select(MCPEvent).where(MCPEvent.server_id == server.id).order_by(MCPEvent.sequence.desc()).limit(100)).scalars().all()
    event_items = [
        event.payload
        | {
            "event_type": event.event_type,
            "sequence": event.sequence,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]
    config = server.config if isinstance(server.config, dict) else {}
    cached_tools = config.get("mcp_tools_cache") if isinstance(config.get("mcp_tools_cache"), list) else []
    return {
        "server": MCPServerRead.model_validate(server).model_dump(mode="json"),
        "diagnostics": {
            "credential_configured": session.execute(
                select(MCPOAuthToken.id).where(MCPOAuthToken.server_id == server.id)
            ).scalar_one_or_none() is not None,
            "oauth_configured": str(config.get("oauth_mode") or "none").lower() != "none" and session.execute(
                select(MCPOAuthToken.id).where(MCPOAuthToken.server_id == server.id)
            ).scalar_one_or_none() is not None,
            "catalog_counts": {
                key.removeprefix("mcp_").removesuffix("_cache"): len(value)
                for key, value in config.items()
                if key.startswith("mcp_") and key.endswith("_cache") and isinstance(value, list)
            },
            "event_counts": dict(Counter(event.event_type for event in events)),
            "latest_event": event_items[0] if event_items else None,
            "reconnect_attempts": int(server.reconnect_attempts or 0),
            "last_error": server.last_error,
            "last_catalog_sync_at": config.get("mcp_catalog_last_sync_at"),
            "active_tools": [
                {
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "input_schema": item.get("inputSchema"),
                }
                for item in cached_tools
                if isinstance(item, dict) and item.get("name")
            ],
        },
        "events": event_items,
    }
