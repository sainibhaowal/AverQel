from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import get_settings
from app.integrations.models.mcp_server import MCPRegistryEntry, MCPServer
from app.integrations.schemas.mcp import MCPCatalogReviewRequest, MCPServerRead
from app.integrations.services.mcp_endpoint_security import (
    MCPEndpointRejectedError,
    validate_remote_endpoint,
)
from app.integrations.services.mcp_oauth_service import MCPServerOAuthService
from app.integrations.services.mcp_provider_auth import get_mcp_provider_profile
from app.integrations.workers.tasks_mcp import refresh_server_catalog
from app.platform.database.session import get_db, set_db_tenant_context

router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = logging.getLogger(__name__)
_SENSITIVE_MARKETPLACE_METADATA_MARKERS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "verifier",
}


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
    if isinstance(entry.documentation_url, str) and entry.documentation_url.strip().startswith(("https://", "http://")):
        return entry.documentation_url.strip()
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


def _marketplace_catalog_metadata(entry: MCPRegistryEntry) -> dict[str, Any]:
    raw = entry.raw_metadata if isinstance(entry.raw_metadata, dict) else {}
    catalog = raw.get("catalog")
    result = dict(catalog) if isinstance(catalog, dict) else {}
    direct_values = {
        "provider_slug": entry.provider_slug,
        "publisher_type": entry.publisher_type,
        "documentation_url": entry.documentation_url,
        "author_website_url": entry.author_website_url,
        "support_url": entry.support_url,
        "privacy_policy_url": entry.privacy_policy_url,
        "trusted_logo_key": entry.trusted_logo_key,
        "supported_products": entry.supported_products,
        "tool_categories": entry.tool_categories,
        "risk_policy": entry.risk_policy,
    }
    for key, value in direct_values.items():
        if value not in (None, [], {}):
            result[key] = value
    if isinstance(entry.catalog_badges, dict) and entry.catalog_badges:
        result["badges"] = entry.catalog_badges
    existing_health = result.get("health") if isinstance(result.get("health"), dict) else {}
    result["health"] = {
        **existing_health,
        "status": entry.health_status,
        "last_checked_at": entry.health_checked_at.isoformat() if entry.health_checked_at else None,
    }
    return result


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_badges(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    allowed = {"official", "community", "new", "trending", "interactive", "developer_preview"}
    return {key: bool(value[key]) for key in allowed if isinstance(value.get(key), bool)}


def _safe_marketplace_metadata(value: object) -> Any:
    """Strip credentials from legacy registry metadata before serializing it."""
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(key).replace("-", "_").casefold()
            if any(marker in normalized_key for marker in _SENSITIVE_MARKETPLACE_METADATA_MARKERS):
                continue
            safe[str(key)] = _safe_marketplace_metadata(nested)
        return safe
    if isinstance(value, list):
        return [_safe_marketplace_metadata(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _marketplace_connectability(entry: MCPRegistryEntry) -> tuple[bool, str | None]:
    """Keep legacy approved entries working while gating curated OAuth profiles.

    A curated provider remains visible before its provider-specific OAuth flow
    exists, but it must never fall back to generic discovery/registration.
    Entries without this explicit metadata preserve the existing approved-entry
    behavior until they are migrated to an explicit readiness state.
    """
    if entry.trust_status != "approved":
        return False, "This provider has not been approved by AverQel."
    if not entry.remote_url:
        return False, "This provider does not publish a remote endpoint."
    profile = get_mcp_provider_profile(entry.provider_slug)
    if profile is not None:
        ready, reason = profile.readiness(get_settings())
        if not ready:
            return False, reason or "Provider-specific OAuth is not configured."
        return True, None
    catalog = _marketplace_catalog_metadata(entry)
    readiness = catalog.get("connection_ready")
    if isinstance(readiness, bool):
        if readiness:
            return True, None
        reason = catalog.get("connection_readiness_reason")
        return False, str(reason) if isinstance(reason, str) and reason.strip() else "Connection setup is not ready."
    return True, None


def _marketplace_entry_payload(entry: MCPRegistryEntry) -> dict[str, Any]:
    """Return public marketplace data without OAuth or connection secrets."""
    catalog = _marketplace_catalog_metadata(entry)
    connectable, connectability_reason = _marketplace_connectability(entry)
    requested_scopes = _safe_string_list(entry.requested_scopes)
    if not requested_scopes:
        requested_scopes = _safe_string_list(
            (entry.oauth_requirements if isinstance(entry.oauth_requirements, dict) else {}).get("requested_scopes")
        )
    return {
        "id": str(entry.id),
        "name": entry.display_name,
        "server_name": entry.server_name,
        "publisher": entry.publisher,
        "description": entry.description,
        "transport": entry.transport,
        "remote_url": entry.remote_url,
        "categories": entry.categories,
        "official": entry.official,
        "verified": entry.verified,
        "source": entry.source,
        "oauth_requirements": _safe_marketplace_metadata(entry.oauth_requirements),
        "package_metadata": _safe_marketplace_metadata(entry.package_metadata),
        "action": "connect" if entry.remote_url else "install",
        "logo_url": entry.logo_url,
        "tool_count": entry.tool_count,
        "last_catalog_sync_at": entry.last_catalog_sync_at.isoformat() if entry.last_catalog_sync_at else None,
        "verification_reason": entry.verification_reason,
        "last_seen_at": entry.last_seen_at.isoformat(),
        "docs_url": _marketplace_docs_url(entry),
        "connection_options": _marketplace_connection_options(entry),
        "capabilities": _marketplace_capabilities(entry),
        "tool_preview": _marketplace_tool_preview(entry),
        "catalog_status": entry.catalog_status,
        "auth_type": _marketplace_auth_type(entry),
        "trust_status": entry.trust_status,
        "verification_source": entry.verification_source,
        "popularity_rank": entry.popularity_rank,
        "provider_slug": catalog.get("provider_slug") if isinstance(catalog.get("provider_slug"), str) else None,
        "publisher_type": catalog.get("publisher_type") if isinstance(catalog.get("publisher_type"), str) else None,
        "author_name": catalog.get("author_name") if isinstance(catalog.get("author_name"), str) else None,
        "author_website_url": catalog.get("author_website_url") if isinstance(catalog.get("author_website_url"), str) else None,
        "support_url": catalog.get("support_url") if isinstance(catalog.get("support_url"), str) else None,
        "privacy_policy_url": catalog.get("privacy_policy_url") if isinstance(catalog.get("privacy_policy_url"), str) else None,
        "badges": _safe_badges(catalog.get("badges")),
        "availability": catalog.get("availability") if isinstance(catalog.get("availability"), str) else None,
        "trusted_logo_key": catalog.get("trusted_logo_key") if isinstance(catalog.get("trusted_logo_key"), str) else None,
        "supported_products": _safe_string_list(catalog.get("supported_products")),
        "tool_categories": _safe_string_list(catalog.get("tool_categories")),
        "risk_policy": catalog.get("risk_policy") if isinstance(catalog.get("risk_policy"), dict) else {},
        "health": catalog.get("health") if isinstance(catalog.get("health"), dict) else {},
        "reviewed_at": catalog.get("reviewed_at") if isinstance(catalog.get("reviewed_at"), str) else None,
        "review_due_at": catalog.get("review_due_at") if isinstance(catalog.get("review_due_at"), str) else None,
        "requested_scopes": requested_scopes,
        "scope_mode": (
            entry.oauth_requirements.get("scope_mode")
            if isinstance(entry.oauth_requirements, dict) and isinstance(entry.oauth_requirements.get("scope_mode"), str)
            else None
        ),
        "scope_note": (
            entry.oauth_requirements.get("scope_note")
            if isinstance(entry.oauth_requirements, dict) and isinstance(entry.oauth_requirements.get("scope_note"), str)
            else None
        ),
        "connectable": connectable,
        "connectability_reason": connectability_reason,
    }


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
    connectable, connectability_reason = _marketplace_connectability(entry)
    if not connectable:
        raise HTTPException(status_code=409, detail=connectability_reason or "This MCP entry is not ready to connect")
    try:
        endpoint = validate_remote_endpoint(entry.remote_url)
    except MCPEndpointRejectedError as exc:
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
        "provider_slug": entry.provider_slug,
        "vendor_slug": entry.provider_slug,
        "source": entry.source,
        "categories": entry.categories or [],
    }
    server = MCPServer(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        registry_entry_id=entry.id,
        provider_slug=entry.provider_slug,
        name=entry.display_name,
        transport="streamable_http",
        config=config,
        account_identity={},
        catalog_revision=0,
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
        except Exception:
            logger.exception("MCP OAuth start failed for server %s", server.id)
            server.status = "needs_auth"
            server.last_error = "MCP OAuth setup failed"
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
        logger.exception("MCP OAuth start request failed for server %s", server_id)
        raise HTTPException(status_code=400, detail="MCP OAuth setup failed") from exc
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
        logger.exception("MCP OAuth callback failed for server %s", server_id)
        raise HTTPException(status_code=400, detail="MCP OAuth callback failed") from exc
    server = session.execute(
        select(MCPServer).where(
            MCPServer.id == server_id,
            MCPServer.tenant_id == tenant_id,
            MCPServer.user_id == uuid.UUID(str(state_payload["user_id"])),
        )
    ).scalar_one_or_none()
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


@router.get("/oauth/callback")
def stable_oauth_callback(code: str, state: str, session: Session = Depends(get_db)):
    """Stable provider callback; server identity comes only from signed state."""
    service = MCPServerOAuthService(session, get_settings())
    try:
        state_payload = service.verify_state(state)
        server_id = uuid.UUID(str(state_payload["mcp_server_id"]))
        tenant_id = uuid.UUID(str(state_payload["tenant_id"]))
        user_id = uuid.UUID(str(state_payload["user_id"]))
        set_db_tenant_context(session, tenant_id)
        server = session.execute(
            select(MCPServer).where(
                MCPServer.id == server_id,
                MCPServer.tenant_id == tenant_id,
                MCPServer.user_id == user_id,
            )
        ).scalar_one_or_none()
        if server is None:
            raise ValueError("MCP server not found")
        service.finish(server=server, code=code, state=state)
    except Exception as exc:
        logger.exception("MCP OAuth callback failed")
        raise HTTPException(status_code=400, detail="MCP OAuth callback failed") from exc
    refresh_server_catalog.delay(str(server.id), str(server.tenant_id))
    origin = (get_settings().averqel_public_origin or "").strip().rstrip("/")
    if origin:
        query = urlencode({"mcp_status": "connected", "server_id": str(server.id)})
        return RedirectResponse(url=f"{origin}/dashboard/mcp?{query}", status_code=303)
    return {"status": "connected", "server_id": str(server.id)}


@router.delete("/servers/{server_id}/oauth", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_oauth(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> Response:
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
    try:
        MCPServerOAuthService(session, get_settings()).disconnect(
            server=server,
            user_id=auth.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="MCP OAuth disconnect failed") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/catalog", response_model=list[dict[str, Any]])
def catalog(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    """Return the synchronized registry catalog, never a hardcoded vendor list."""
    set_db_tenant_context(session, auth.tenant_id)
    rows = session.execute(select(MCPRegistryEntry).where(MCPRegistryEntry.remote_url.is_not(None), MCPRegistryEntry.trust_status == "approved").order_by(MCPRegistryEntry.display_name)).scalars().all()
    return [_marketplace_entry_payload(row) for row in rows]

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
    if q:
        query = query.where(
            MCPRegistryEntry.display_name.ilike(f"%{q}%")
            | MCPRegistryEntry.description.ilike(f"%{q}%")
        )
    if transport:
        query = query.where(MCPRegistryEntry.transport == transport)
    if official is not None:
        query = query.where(MCPRegistryEntry.official.is_(official))
    if verified is not None:
        query = query.where(MCPRegistryEntry.verified.is_(verified))
    rows = session.execute(query.order_by(MCPRegistryEntry.display_name)).scalars().all()
    if category:
        rows = [
            r for r in rows
            if category.lower() in [str(x).lower() for x in (r.categories or [])]
        ]
    if auth_type:
        rows = [r for r in rows if _marketplace_auth_type(r) == auth_type]
    if trust_status:
        rows = [r for r in rows if r.trust_status == trust_status]
    if sort == "alphabetical":
        rows.sort(key=lambda row: row.display_name.casefold())
    elif sort == "popular":
        rows.sort(key=lambda row: (row.popularity_rank is None, row.popularity_rank or 1_000_000, row.display_name.casefold()))
    elif sort in {"trending", "new"}:
        rows.sort(key=lambda row: (row.last_seen_at is None, row.last_seen_at), reverse=True)
    else:
        rows.sort(key=lambda row: (row.popularity_rank is None, row.popularity_rank or 1_000_000, row.display_name.casefold()))
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    return {"items": [_marketplace_entry_payload(row) for row in rows],
        "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}

@router.post(
    "/catalog/{entry_id}/review",
    response_model=dict[str, Any],
    dependencies=[Depends(require_permissions("mcp:catalog:manage"))],
)
def review_catalog_entry(
    entry_id: uuid.UUID,
    payload: MCPCatalogReviewRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
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

    from app.integrations.models.mcp_server import MCPEvent, MCPOAuthToken
    set_db_tenant_context(session, auth.tenant_id)
    server = session.execute(select(MCPServer).where(MCPServer.id == server_id, MCPServer.tenant_id == auth.tenant_id, MCPServer.user_id == auth.user_id)).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    events = session.execute(select(MCPEvent).where(MCPEvent.server_id == server.id).order_by(MCPEvent.sequence.desc()).limit(100)).scalars().all()
    safe_payload_keys = {
        "tool",
        "argument_keys",
        "error_code",
        "content_item_count",
        "content_types",
        "has_structured_content",
        "rendered_length",
        "is_error",
        "has_refresh_token",
        "expires_in",
        "provider",
    }
    event_items = []
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        event_items.append(
            {
                key: payload[key]
                for key in safe_payload_keys
                if key in payload
            }
            | {
                "event_type": event.event_type,
                "sequence": event.sequence,
                "created_at": event.created_at.isoformat(),
            }
        )
    config = server.config if isinstance(server.config, dict) else {}
    cached_tools = config.get("mcp_tools_cache") if isinstance(config.get("mcp_tools_cache"), list) else []
    return {
        "server": MCPServerRead.model_validate(server).model_dump(mode="json"),
        "diagnostics": {
            "credential_configured": session.execute(
                select(MCPOAuthToken.id).where(
                    MCPOAuthToken.server_id == server.id,
                    MCPOAuthToken.tenant_id == auth.tenant_id,
                    MCPOAuthToken.user_id == auth.user_id,
                )
            ).scalar_one_or_none() is not None,
            "oauth_configured": str(config.get("oauth_mode") or "none").lower() != "none" and session.execute(
                select(MCPOAuthToken.id).where(
                    MCPOAuthToken.server_id == server.id,
                    MCPOAuthToken.tenant_id == auth.tenant_id,
                    MCPOAuthToken.user_id == auth.user_id,
                )
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
