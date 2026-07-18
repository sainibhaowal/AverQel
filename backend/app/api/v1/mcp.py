from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, get_auth_context
from app.db.session import get_db, set_db_tenant_context
from app.models.integrations.mcp_server import MCPServer, MCPRegistryEntry
from app.worker.tasks_mcp import refresh_server_catalog
from app.services.integrations.mcp_registry import get_official_vendor, list_official_vendors
from app.services.integrations.mcp_oauth_service import MCPServerOAuthService
from app.core.config import get_settings
from app.services.integrations.mcp_registry_sync import sync_registry
from app.services.integrations.mcp_endpoint_security import validate_remote_endpoint, MCPEndpointRejected

router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPServerCreate(BaseModel):
    vendor_slug: str = Field(min_length=1, max_length=80)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

class MCPRemoteInstall(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    endpoint: str
    oauth_mode: str = "none"
    categories: list[str] = Field(default_factory=list)


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
            if key.lower() in sensitive or any(marker in key.lower() for marker in ("token", "secret", "verifier")):
                return "[REDACTED]"
            if isinstance(item, dict):
                return {str(k): redact(v, str(k)) for k, v in item.items()}
            if isinstance(item, list):
                return [redact(v, key) for v in item]
            return item

        return redact(value) if isinstance(value, dict) else {}


@router.get("/servers", response_model=list[MCPServerRead])
def list_servers(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    return list(session.execute(select(MCPServer).where(MCPServer.tenant_id == auth.tenant_id, MCPServer.user_id == auth.user_id).order_by(MCPServer.created_at.desc())).scalars().all())


@router.post("/servers", response_model=MCPServerRead, status_code=201)
def install_server(payload: MCPServerCreate, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    vendor = get_official_vendor(payload.vendor_slug)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Only curated official MCP vendors can be installed")
    if not vendor.get("server_url"):
        raise HTTPException(status_code=409, detail={"message": "This vendor requires official client registration", "docs_url": vendor["docs_url"]})
    config = {**payload.config, "server_url": vendor["server_url"], "vendor_slug": vendor["slug"], "official": True, "oauth_mode": vendor["oauth"]}
    existing = session.execute(
        select(MCPServer).where(
            MCPServer.tenant_id == auth.tenant_id,
            MCPServer.user_id == auth.user_id,
            MCPServer.config["vendor_slug"].as_string() == vendor["slug"],
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    server = MCPServer(tenant_id=auth.tenant_id, user_id=auth.user_id, name=str(vendor["name"]), transport=str(vendor["transport"]), config=config, enabled=payload.enabled)
    session.add(server)
    session.commit()
    session.refresh(server)
    if vendor.get("oauth") == "none":
        refresh_server_catalog.delay(str(server.id), str(auth.tenant_id))
    return server

@router.post("/servers/custom-remote", response_model=MCPServerRead, status_code=201)
def install_custom_remote(payload: MCPRemoteInstall, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    """Install a tenant-owned HTTPS MCP endpoint after SSRF validation."""
    set_db_tenant_context(session, auth.tenant_id)
    try:
        endpoint = validate_remote_endpoint(payload.endpoint)
    except MCPEndpointRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    server = MCPServer(tenant_id=auth.tenant_id, user_id=auth.user_id, name=payload.name,
                       transport="streamable_http", config={"server_url": endpoint, "oauth_mode": payload.oauth_mode,
                       "custom": True, "categories": sorted({x.strip().lower() for x in payload.categories if x.strip()})},
                       enabled=True, status="needs_auth" if payload.oauth_mode != "none" else "disconnected")
    session.add(server); session.commit(); session.refresh(server)
    if payload.oauth_mode == "none": refresh_server_catalog.delay(str(server.id), str(auth.tenant_id))
    return server


@router.post("/servers/{server_id}/refresh", response_model=dict[str, Any])
def refresh_server(server_id: uuid.UUID, background_tasks: BackgroundTasks, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
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
def official_catalog(_auth: AuthContext = Depends(get_auth_context)):
    return list_official_vendors()

@router.get("/marketplace", response_model=dict[str, Any])
def marketplace(q: str | None = None, category: str | None = None, transport: str | None = None,
                official: bool | None = None, verified: bool | None = None, page: int = 1,
                page_size: int = 24, session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    page, page_size = max(1, page), min(100, max(1, page_size))
    query = select(MCPRegistryEntry)
    if q: query = query.where(MCPRegistryEntry.display_name.ilike(f"%{q}%") | MCPRegistryEntry.description.ilike(f"%{q}%"))
    if transport: query = query.where(MCPRegistryEntry.transport == transport)
    if official is not None: query = query.where(MCPRegistryEntry.official.is_(official))
    if verified is not None: query = query.where(MCPRegistryEntry.verified.is_(verified))
    rows = session.execute(query.order_by(MCPRegistryEntry.display_name)).scalars().all()
    if category: rows = [r for r in rows if category.lower() in [str(x).lower() for x in (r.categories or [])]]
    total = len(rows); rows = rows[(page - 1) * page_size: page * page_size]
    return {"items": [{"id": str(r.id), "name": r.display_name, "server_name": r.server_name, "publisher": r.publisher,
        "description": r.description, "transport": r.transport, "remote_url": r.remote_url,
        "categories": r.categories, "official": r.official, "verified": r.verified,
        "oauth_requirements": r.oauth_requirements, "package_metadata": r.package_metadata,
        "action": "connect" if r.remote_url else "setup_required", "logo_url": r.logo_url,
        "tool_count": r.tool_count, "last_catalog_sync_at": r.last_catalog_sync_at.isoformat() if r.last_catalog_sync_at else None,
        "verification_reason": r.verification_reason, "last_seen_at": r.last_seen_at.isoformat()} for r in rows],
        "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}

@router.post("/marketplace/sync", response_model=dict[str, int])
def sync_marketplace(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    return {"synced": sync_registry(session)}


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
    return {
        "server": MCPServerRead.model_validate(server).model_dump(mode="json"),
        "diagnostics": {
            "oauth_configured": session.execute(
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
        },
        "events": event_items,
    }
