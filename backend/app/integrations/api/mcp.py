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
from app.deepspace.models.mission_snapshot import DeepSpaceMissionSnapshot
from app.integrations.models.mcp_connection_policy import MCPConnectionPolicy
from app.integrations.models.mcp_server import MCPOAuthToken, MCPRegistryEntry, MCPServer
from app.integrations.schemas.mcp import (
    MCPActionResponse,
    MCPCatalogReviewRead,
    MCPCatalogReviewRequest,
    MCPConnectionCreateResponse,
    MCPConnectionOverrideRead,
    MCPConnectionOverrideUpdate,
    MCPConnectionPolicyRead,
    MCPConnectionPolicyUpdate,
    MCPConnectionRead,
    MCPInspectorRead,
    MCPMarketplaceEntryRead,
    MCPMarketplaceFacetsRead,
    MCPMarketplacePageRead,
    MCPOAuthStartResponse,
    MCPScopedConnectionListRead,
    MCPScopedConnectionRead,
    MCPServerRead,
    MCPToolCatalogRead,
    MCPToolPolicyUpdate,
    MCPToolRead,
)
from app.integrations.services.mcp_endpoint_security import (
    MCPEndpointRejectedError,
    validate_remote_endpoint,
)
from app.integrations.services.mcp_oauth_service import MCPServerOAuthService
from app.integrations.services.mcp_provider_auth import get_mcp_provider_profile
from app.integrations.workers.tasks_mcp import refresh_server_catalog
from app.platform.database.session import get_db, set_db_tenant_context
from app.query.models.conversation import Conversation

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
    return [
        {
            "name": str(item.get("name") or "").strip(),
            "description": str(item.get("description") or "").strip() or None,
            "category": str(item.get("category") or "").strip() or None,
            "risk_labels": _safe_string_list(item.get("risk_labels")),
        }
        for item in preview
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]


def _marketplace_tools(entry: MCPRegistryEntry) -> list[dict[str, Any]]:
    """Return only the complete reviewed tool catalog for this entry.

    Live MCP discovery is intentionally not used for marketplace metadata.
    The catalog worker writes reviewed ``tools`` data; ``tool_preview`` is a
    compatibility fallback for older curated rows.
    """
    package = entry.package_metadata if isinstance(entry.package_metadata, dict) else {}
    values = package.get("tools")
    if not isinstance(values, list):
        values = package.get("tool_preview")
    if not isinstance(values, list):
        return []
    return [
        {
            "name": str(item.get("name") or "").strip(),
            "description": str(item.get("description") or "").strip() or None,
            "category": str(item.get("category") or "").strip() or None,
            "risk_labels": _safe_string_list(item.get("risk_labels")),
        }
        for item in values
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]


def _marketplace_auth_type(entry: MCPRegistryEntry) -> str:
    requirements = entry.oauth_requirements if isinstance(entry.oauth_requirements, dict) else {}
    return str(requirements.get("type") or "setup_required")


def _marketplace_docs_url(entry: MCPRegistryEntry) -> str | None:
    if isinstance(entry.documentation_url, str) and entry.documentation_url.strip().startswith(
        ("https://", "http://")
    ):
        return entry.documentation_url.strip()
    raw = entry.raw_metadata if isinstance(entry.raw_metadata, dict) else {}
    server = raw.get("server") if isinstance(raw.get("server"), dict) else raw
    for key in (
        "documentationUrl",
        "documentation_url",
        "docsUrl",
        "docs_url",
        "documentation",
        "homepage",
    ):
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
        options.append(
            {
                "transport": remote.get("type") or "streamable_http",
                "url": url,
                "security_schemes": _safe_marketplace_metadata(remote.get("securitySchemes") or {}),
            }
        )
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
    result["health"] = {
        "status": entry.health_status,
        "last_checked_at": entry.health_checked_at.isoformat() if entry.health_checked_at else None,
    }
    if entry.health_status == "not_checked":
        result["health"]["detail"] = "Live health is checked only after user authentication."
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


def _safe_marketplace_package_metadata(entry: MCPRegistryEntry) -> dict[str, Any]:
    package = entry.package_metadata if isinstance(entry.package_metadata, dict) else {}
    allowed = {
        "provider_slug",
        "auth_type",
        "supported_products",
        "tool_categories",
        "tool_preview",
        "discovered_capabilities",
    }
    safe = {key: package[key] for key in allowed if key in package}
    safe["tool_preview"] = _marketplace_tool_preview(entry)
    safe["tools"] = _marketplace_tools(entry)
    return _safe_marketplace_metadata(safe)


def _safe_marketplace_oauth_requirements(entry: MCPRegistryEntry) -> dict[str, Any]:
    requirements = entry.oauth_requirements if isinstance(entry.oauth_requirements, dict) else {}
    allowed = {"type", "requested_scopes", "scope_mode", "scope_note"}
    safe = {key: requirements[key] for key in allowed if key in requirements}
    safe["requested_scopes"] = _safe_string_list(entry.requested_scopes) or _safe_string_list(
        requirements.get("requested_scopes")
    )
    return _safe_marketplace_metadata(safe)


def _policy_defaults(server: MCPServer) -> MCPConnectionPolicy:
    return MCPConnectionPolicy(
        tenant_id=server.tenant_id,
        user_id=server.user_id,
        server_id=server.id,
        allowed_tools=[],
        denied_tools=[],
        read_only=True,
        risk_ceiling="read",
        approval_rules={
            "write": "needs_approval",
            "delete": "needs_approval",
            "external_message": "needs_approval",
        },
        tool_modes={},
        # A user-authorized connection is available to that user's DeepSpace
        # conversations by default. Tool-level policy and approvals remain
        # enforced at execution time.
        default_enabled=True,
        deepspace_overrides={},
        conversation_overrides={},
    )


def _get_policy(session: Session, server: MCPServer, *, create: bool) -> MCPConnectionPolicy | None:
    policy = session.execute(
        select(MCPConnectionPolicy).where(
            MCPConnectionPolicy.server_id == server.id,
            MCPConnectionPolicy.tenant_id == server.tenant_id,
            MCPConnectionPolicy.user_id == server.user_id,
        )
    ).scalar_one_or_none()
    if policy is None and create:
        policy = _policy_defaults(server)
        session.add(policy)
        session.flush()
        server.connection_policy_id = policy.id
    return policy


def _connection_payload(session: Session, server: MCPServer) -> MCPConnectionRead:
    policy = _get_policy(session, server, create=False)
    token = session.execute(
        select(MCPOAuthToken).where(
            MCPOAuthToken.server_id == server.id,
            MCPOAuthToken.tenant_id == server.tenant_id,
            MCPOAuthToken.user_id == server.user_id,
        )
    ).scalar_one_or_none()
    granted_scopes = []
    if token is not None and isinstance(token.granted_scopes, list):
        granted_scopes = sorted(
            {str(scope).strip() for scope in token.granted_scopes if str(scope).strip()}
        )
    return MCPConnectionRead.model_validate(server).model_copy(
        update={
            "policy": MCPConnectionPolicyRead.model_validate(policy) if policy else None,
            "granted_scopes": granted_scopes,
        }
    )


def _owned_server(session: Session, auth: AuthContext, server_id: uuid.UUID) -> MCPServer:
    server = session.execute(
        select(MCPServer).where(
            MCPServer.id == server_id,
            MCPServer.tenant_id == auth.tenant_id,
            MCPServer.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


def _tool_payload(server: MCPServer, tool_name: str, mode: str) -> MCPToolRead:
    config = server.config if isinstance(server.config, dict) else {}
    cached_tools = (
        config.get("mcp_tools_cache") if isinstance(config.get("mcp_tools_cache"), list) else []
    )
    item = next(
        (
            value
            for value in cached_tools
            if isinstance(value, dict) and value.get("name") == tool_name
        ),
        None,
    )
    item = item or {"name": tool_name}
    risk_labels = _safe_string_list(item.get("risk_labels"))
    return MCPToolRead(
        name=tool_name,
        description=str(item.get("description") or "").strip() or None,
        category=str(item.get("category") or "").strip() or None,
        risk_labels=risk_labels,
        mode=mode if mode in {"always_allow", "needs_approval", "blocked"} else "needs_approval",
    )


def _scope_owner(session: Session, auth: AuthContext, scope: str, scope_id: uuid.UUID) -> None:
    model = DeepSpaceMissionSnapshot if scope == "deepspace" else Conversation
    id_column = model.mission_id if scope == "deepspace" else model.id
    owner = session.execute(
        select(id_column).where(
            id_column == scope_id,
            model.tenant_id == auth.tenant_id,
            model.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail=f"{scope.title()} not found")


def _apply_policy_update(policy: MCPConnectionPolicy, payload: MCPConnectionPolicyUpdate) -> None:
    policy.allowed_tools = list(dict.fromkeys(payload.allowed_tools))
    policy.denied_tools = list(dict.fromkeys(payload.denied_tools))
    policy.read_only = payload.read_only
    policy.risk_ceiling = payload.risk_ceiling
    policy.approval_rules = payload.approval_rules or {
        "write": "needs_approval",
        "delete": "needs_approval",
        "external_message": "needs_approval",
    }
    policy.tool_modes = dict(payload.tool_modes)
    policy.default_enabled = payload.default_enabled
    policy.deepspace_overrides = dict(payload.deepspace_overrides)
    policy.conversation_overrides = dict(payload.conversation_overrides)
    policy.updated_at = datetime.now(UTC)


def _tool_mode(policy: MCPConnectionPolicy | None, tool_name: str) -> str:
    if policy is None:
        return "needs_approval"
    if tool_name in (policy.denied_tools or []):
        return "blocked"
    configured = (policy.tool_modes or {}).get(tool_name)
    return (
        configured
        if configured in {"always_allow", "needs_approval", "blocked"}
        else "needs_approval"
    )


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
        return False, (
            str(reason)
            if isinstance(reason, str) and reason.strip()
            else "Connection setup is not ready."
        )
    return True, None


def _marketplace_entry_payload(entry: MCPRegistryEntry) -> dict[str, Any]:
    """Return public marketplace data without OAuth or connection secrets."""
    catalog = _marketplace_catalog_metadata(entry)
    connectable, connectability_reason = _marketplace_connectability(entry)
    requested_scopes = _safe_string_list(entry.requested_scopes)
    if not requested_scopes:
        requested_scopes = _safe_string_list(
            (entry.oauth_requirements if isinstance(entry.oauth_requirements, dict) else {}).get(
                "requested_scopes"
            )
        )
    logo_url = None
    if catalog.get("publisher_type") == "community" and isinstance(entry.logo_url, str):
        try:
            logo_url = validate_remote_endpoint(entry.logo_url)
        except MCPEndpointRejectedError:
            logo_url = None
    return {
        "id": str(entry.id),
        "name": entry.display_name,
        "version": entry.version,
        "server_name": entry.server_name,
        "publisher": entry.publisher,
        "description": entry.description,
        "transport": entry.transport,
        "remote_url": entry.remote_url,
        "categories": entry.categories,
        "official": entry.official,
        "verified": entry.verified,
        "source": entry.source,
        "oauth_requirements": _safe_marketplace_oauth_requirements(entry),
        "package_metadata": _safe_marketplace_package_metadata(entry),
        "action": "connect" if entry.remote_url else "install",
        # Curated logos are resolved by the frontend from ``trusted_logo_key``;
        # never pass through an arbitrary registry-hosted image URL.
        "logo_url": logo_url,
        "tool_count": entry.tool_count,
        "last_catalog_sync_at": (
            entry.last_catalog_sync_at.isoformat() if entry.last_catalog_sync_at else None
        ),
        "verification_reason": entry.verification_reason,
        "last_seen_at": entry.last_seen_at.isoformat(),
        "docs_url": _marketplace_docs_url(entry),
        "connection_options": _marketplace_connection_options(entry),
        "capabilities": _marketplace_capabilities(entry),
        "tool_preview": _marketplace_tool_preview(entry),
        "tools": _marketplace_tools(entry),
        "catalog_status": entry.catalog_status,
        "auth_type": _marketplace_auth_type(entry),
        "trust_status": entry.trust_status,
        "verification_source": entry.verification_source,
        "popularity_rank": entry.popularity_rank,
        "provider_slug": (
            catalog.get("provider_slug") if isinstance(catalog.get("provider_slug"), str) else None
        ),
        "publisher_type": (
            catalog.get("publisher_type")
            if isinstance(catalog.get("publisher_type"), str)
            else None
        ),
        "author_name": (
            catalog.get("author_name") if isinstance(catalog.get("author_name"), str) else None
        ),
        "author_website_url": (
            catalog.get("author_website_url")
            if isinstance(catalog.get("author_website_url"), str)
            else None
        ),
        "support_url": (
            catalog.get("support_url") if isinstance(catalog.get("support_url"), str) else None
        ),
        "privacy_policy_url": (
            catalog.get("privacy_policy_url")
            if isinstance(catalog.get("privacy_policy_url"), str)
            else None
        ),
        "badges": _safe_badges(catalog.get("badges")),
        "availability": (
            catalog.get("availability") if isinstance(catalog.get("availability"), str) else None
        ),
        "trusted_logo_key": (
            catalog.get("trusted_logo_key")
            if isinstance(catalog.get("trusted_logo_key"), str)
            else None
        ),
        "supported_products": _safe_string_list(catalog.get("supported_products")),
        "tool_categories": _safe_string_list(catalog.get("tool_categories")),
        "risk_policy": (
            catalog.get("risk_policy") if isinstance(catalog.get("risk_policy"), dict) else {}
        ),
        "health": catalog.get("health") if isinstance(catalog.get("health"), dict) else {},
        "reviewed_at": (
            catalog.get("reviewed_at") if isinstance(catalog.get("reviewed_at"), str) else None
        ),
        "review_due_at": (
            catalog.get("review_due_at") if isinstance(catalog.get("review_due_at"), str) else None
        ),
        "requested_scopes": requested_scopes,
        "scope_mode": (
            entry.oauth_requirements.get("scope_mode")
            if isinstance(entry.oauth_requirements, dict)
            and isinstance(entry.oauth_requirements.get("scope_mode"), str)
            else None
        ),
        "scope_note": (
            entry.oauth_requirements.get("scope_note")
            if isinstance(entry.oauth_requirements, dict)
            and isinstance(entry.oauth_requirements.get("scope_note"), str)
            else None
        ),
        "connectable": connectable,
        "connectability_reason": connectability_reason,
    }


@router.get("/servers", response_model=list[MCPConnectionRead])
def list_servers(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    set_db_tenant_context(session, auth.tenant_id)
    servers = list(
        session.execute(
            select(MCPServer)
            .where(
                MCPServer.tenant_id == auth.tenant_id,
                MCPServer.user_id == auth.user_id,
            )
            .order_by(MCPServer.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_connection_payload(session, server) for server in servers]


@router.get("/servers/{server_id}", response_model=MCPConnectionRead)
def get_server(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    return _connection_payload(session, _owned_server(session, auth, server_id))


@router.get("/servers/{server_id}/policy", response_model=MCPConnectionPolicyRead)
def get_server_policy(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    server = _owned_server(session, auth, server_id)
    policy = _get_policy(session, server, create=True)
    session.commit()
    # Tenant context is transaction-local; restore it before refreshing or
    # serializing ORM state after the commit.
    set_db_tenant_context(session, auth.tenant_id)
    session.refresh(policy)
    return policy


@router.put("/servers/{server_id}/policy", response_model=MCPConnectionPolicyRead)
def update_server_policy(
    server_id: uuid.UUID,
    payload: MCPConnectionPolicyUpdate,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    server = _owned_server(session, auth, server_id)
    policy = _get_policy(session, server, create=True)
    _apply_policy_update(policy, payload)
    session.commit()
    set_db_tenant_context(session, auth.tenant_id)
    session.refresh(policy)
    return policy


@router.get("/servers/{server_id}/tools", response_model=MCPToolCatalogRead)
def list_server_tools(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    server = _owned_server(session, auth, server_id)
    policy = _get_policy(session, server, create=False)
    config = server.config if isinstance(server.config, dict) else {}
    cached_tools = (
        config.get("mcp_tools_cache") if isinstance(config.get("mcp_tools_cache"), list) else []
    )
    tools = [
        _tool_payload(server, str(item["name"]), _tool_mode(policy, str(item["name"])))
        for item in cached_tools
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    return MCPToolCatalogRead(
        server_id=server.id,
        catalog_revision=int(server.catalog_revision or 0),
        tools=tools,
    )


@router.put("/servers/{server_id}/tools/{tool_name}/policy", response_model=MCPToolRead)
def update_server_tool_policy(
    server_id: uuid.UUID,
    tool_name: str,
    payload: MCPToolPolicyUpdate,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    server = _owned_server(session, auth, server_id)
    normalized_tool_name = tool_name.strip()
    if not normalized_tool_name or len(normalized_tool_name) > 240:
        raise HTTPException(status_code=422, detail="Invalid MCP tool name")
    config = server.config if isinstance(server.config, dict) else {}
    cached_tools = (
        config.get("mcp_tools_cache") if isinstance(config.get("mcp_tools_cache"), list) else []
    )
    known_tools = {
        str(item.get("name"))
        for item in cached_tools
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    if normalized_tool_name not in known_tools:
        raise HTTPException(
            status_code=404, detail="MCP tool is not present in the current catalog"
        )
    policy = _get_policy(session, server, create=True)
    modes = dict(policy.tool_modes or {})
    modes[normalized_tool_name] = payload.mode
    policy.tool_modes = modes
    policy.updated_at = datetime.now(UTC)
    session.commit()
    set_db_tenant_context(session, auth.tenant_id)
    return _tool_payload(server, normalized_tool_name, payload.mode)


def _scoped_connections(
    session: Session,
    auth: AuthContext,
    *,
    scope: Literal["deepspace", "conversation"],
    scope_id: uuid.UUID,
) -> MCPScopedConnectionListRead:
    _scope_owner(session, auth, scope, scope_id)
    servers = (
        session.execute(
            select(MCPServer)
            .where(
                MCPServer.tenant_id == auth.tenant_id,
                MCPServer.user_id == auth.user_id,
            )
            .order_by(MCPServer.created_at.desc())
        )
        .scalars()
        .all()
    )
    connections: list[MCPScopedConnectionRead] = []
    key = str(scope_id)
    for server in servers:
        policy = _get_policy(session, server, create=False)
        overrides = (
            (policy.deepspace_overrides if scope == "deepspace" else policy.conversation_overrides)
            if policy
            else {}
        )
        enabled = (
            bool(overrides.get(key))
            if isinstance(overrides, dict) and isinstance(overrides.get(key), bool)
            else False
        )
        connections.append(
            MCPScopedConnectionRead(
                server=_connection_payload(session, server),
                enabled=enabled,
            )
        )
    return MCPScopedConnectionListRead(scope=scope, scope_id=scope_id, connections=connections)


def _set_scoped_connection(
    session: Session,
    auth: AuthContext,
    *,
    scope: Literal["deepspace", "conversation"],
    scope_id: uuid.UUID,
    server_id: uuid.UUID,
    payload: MCPConnectionOverrideUpdate,
) -> MCPConnectionOverrideRead:
    _scope_owner(session, auth, scope, scope_id)
    server = _owned_server(session, auth, server_id)
    policy = _get_policy(session, server, create=True)
    key = str(scope_id)
    if scope == "deepspace":
        overrides = dict(policy.deepspace_overrides or {})
        overrides[key] = payload.enabled
        policy.deepspace_overrides = overrides
    else:
        overrides = dict(policy.conversation_overrides or {})
        overrides[key] = payload.enabled
        policy.conversation_overrides = overrides
    policy.updated_at = datetime.now(UTC)
    session.commit()
    return MCPConnectionOverrideRead(
        scope=scope,
        scope_id=scope_id,
        server_id=server.id,
        enabled=payload.enabled,
    )


@router.get("/deepspaces/{deepspace_id}/connections", response_model=MCPScopedConnectionListRead)
def list_deepspace_connections(
    deepspace_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    return _scoped_connections(session, auth, scope="deepspace", scope_id=deepspace_id)


@router.put(
    "/deepspaces/{deepspace_id}/connections/{server_id}", response_model=MCPConnectionOverrideRead
)
def update_deepspace_connection(
    deepspace_id: uuid.UUID,
    server_id: uuid.UUID,
    payload: MCPConnectionOverrideUpdate,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    return _set_scoped_connection(
        session,
        auth,
        scope="deepspace",
        scope_id=deepspace_id,
        server_id=server_id,
        payload=payload,
    )


@router.get(
    "/conversations/{conversation_id}/connections", response_model=MCPScopedConnectionListRead
)
def list_conversation_connections(
    conversation_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    return _scoped_connections(session, auth, scope="conversation", scope_id=conversation_id)


@router.put(
    "/conversations/{conversation_id}/connections/{server_id}",
    response_model=MCPConnectionOverrideRead,
)
def update_conversation_connection(
    conversation_id: uuid.UUID,
    server_id: uuid.UUID,
    payload: MCPConnectionOverrideUpdate,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    return _set_scoped_connection(
        session,
        auth,
        scope="conversation",
        scope_id=conversation_id,
        server_id=server_id,
        payload=payload,
    )


@router.post(
    "/marketplace/{entry_id}/connect", response_model=MCPConnectionCreateResponse, status_code=201
)
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
        raise HTTPException(
            status_code=403, detail="Only AverQel-approved MCP entries can be connected"
        )
    if not entry.remote_url:
        raise HTTPException(
            status_code=409, detail="This MCP entry does not publish a remote endpoint"
        )
    connectable, connectability_reason = _marketplace_connectability(entry)
    if not connectable:
        raise HTTPException(
            status_code=409,
            detail=connectability_reason or "This MCP entry is not ready to connect",
        )
    try:
        endpoint = validate_remote_endpoint(entry.remote_url)
    except MCPEndpointRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    auth_type = _marketplace_auth_type(entry)
    if auth_type not in {"anonymous", "oauth"}:
        raise HTTPException(
            status_code=409,
            detail="This Google Workspace MCP entry is not ready for a supported connection",
        )
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
    session.flush()
    _get_policy(session, server, create=True)
    session.commit()
    set_db_tenant_context(session, auth.tenant_id)
    session.refresh(server)
    result = MCPConnectionCreateResponse(
        server=_connection_payload(session, server),
    )
    if oauth_mode == "none":
        refresh_server_catalog.delay(str(server.id), str(auth.tenant_id))
    else:
        try:
            result.authorization_url = MCPServerOAuthService(session, get_settings()).start(
                server=server,
                user_id=auth.user_id,
            )
        except Exception:
            logger.exception("MCP OAuth start failed for server %s", server.id)
            server.status = "needs_auth"
            server.last_error = "MCP OAuth setup failed"
            session.commit()
            set_db_tenant_context(session, auth.tenant_id)
            result.setup_required = True
    # OAuth setup writes its transaction and lifecycle event in one or more
    # commits.  ``set_config(..., true)`` is transaction-local, so every
    # commit clears the RLS tenant context.  Rebind it before serializing the
    # response; otherwise the policy query is evaluated with an empty UUID and
    # PostgreSQL returns ``invalid input syntax for type uuid: \"\"``.
    set_db_tenant_context(session, auth.tenant_id)
    result.server = _connection_payload(session, server)
    return result


@router.post("/servers/{server_id}/refresh", response_model=MCPActionResponse)
def refresh_server(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
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
    refresh_server_catalog.delay(str(server.id), str(auth.tenant_id))
    return MCPActionResponse(status="scheduled", server_id=server.id)


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


@router.post("/servers/{server_id}/oauth/start", response_model=MCPOAuthStartResponse)
def start_oauth(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
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
        url = MCPServerOAuthService(session, get_settings()).start(
            server=server, user_id=auth.user_id
        )
    except Exception as exc:
        logger.exception("MCP OAuth start request failed for server %s", server_id)
        raise HTTPException(status_code=400, detail="MCP OAuth setup failed") from exc
    return MCPOAuthStartResponse(authorization_url=url)


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


@router.get("/catalog", response_model=list[MCPMarketplaceEntryRead])
def catalog(session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)):
    """Return the synchronized registry catalog, never a hardcoded vendor list."""
    set_db_tenant_context(session, auth.tenant_id)
    rows = (
        session.execute(
            select(MCPRegistryEntry)
            .where(
                MCPRegistryEntry.remote_url.is_not(None),
                MCPRegistryEntry.trust_status == "approved",
            )
            .order_by(MCPRegistryEntry.display_name)
        )
        .scalars()
        .all()
    )
    return [_marketplace_entry_payload(row) for row in rows]


@router.get("/marketplace/facets", response_model=MCPMarketplaceFacetsRead)
def marketplace_facets(
    session: Session = Depends(get_db), auth: AuthContext = Depends(get_auth_context)
):
    """Return filter values from catalog data, never from a vendor allowlist."""
    set_db_tenant_context(session, auth.tenant_id)
    rows = (
        session.execute(
            select(MCPRegistryEntry).where(
                MCPRegistryEntry.remote_url.is_not(None),
                MCPRegistryEntry.trust_status == "approved",
            )
        )
        .scalars()
        .all()
    )
    categories = sorted(
        {
            str(category)
            for row in rows
            for category in (row.categories or [])
            if str(category).strip()
        }
    )
    transports = sorted({row.transport for row in rows if row.transport})
    auth_types = sorted({_marketplace_auth_type(row) for row in rows})
    trust_statuses = sorted({row.trust_status for row in rows if row.trust_status})
    return MCPMarketplaceFacetsRead(
        categories=categories,
        transports=transports,
        auth_types=auth_types,
        trust_statuses=trust_statuses,
    )


@router.get("/marketplace/{entry_id}", response_model=MCPMarketplaceEntryRead)
def marketplace_detail(
    entry_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    entry = session.execute(
        select(MCPRegistryEntry).where(
            MCPRegistryEntry.id == entry_id,
            MCPRegistryEntry.remote_url.is_not(None),
            MCPRegistryEntry.trust_status == "approved",
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="MCP marketplace entry not found")
    return _marketplace_entry_payload(entry)


@router.get("/marketplace", response_model=MCPMarketplacePageRead)
def marketplace(
    q: str | None = None,
    category: str | None = None,
    transport: str | None = None,
    official: bool | None = None,
    verified: bool | None = None,
    auth_type: str | None = None,
    trust_status: str | None = None,
    sort: Literal["default", "popular", "trending", "new", "alphabetical"] = "default",
    page: int = 1,
    page_size: int = 24,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    set_db_tenant_context(session, auth.tenant_id)
    page, page_size = max(1, page), min(100, max(1, page_size))
    # Public users see only records approved by AverQel. Registry intake rows
    # remain internal until source, ownership, endpoint, and auth are checked.
    query = select(MCPRegistryEntry).where(
        MCPRegistryEntry.remote_url.is_not(None), MCPRegistryEntry.trust_status == "approved"
    )
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
            r for r in rows if category.lower() in [str(x).lower() for x in (r.categories or [])]
        ]
    if auth_type:
        rows = [r for r in rows if _marketplace_auth_type(r) == auth_type]
    if trust_status:
        rows = [r for r in rows if r.trust_status == trust_status]
    if sort == "alphabetical":
        rows.sort(key=lambda row: row.display_name.casefold())
    elif sort == "popular":
        rows.sort(
            key=lambda row: (
                row.popularity_rank is None,
                row.popularity_rank or 1_000_000,
                row.display_name.casefold(),
            )
        )
    elif sort in {"trending", "new"}:
        rows.sort(key=lambda row: (row.last_seen_at is None, row.last_seen_at), reverse=True)
    else:
        rows.sort(
            key=lambda row: (
                row.popularity_rank is None,
                row.popularity_rank or 1_000_000,
                row.display_name.casefold(),
            )
        )
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    return MCPMarketplacePageRead(
        items=[_marketplace_entry_payload(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=(total + page_size - 1) // page_size,
    )


@router.post(
    "/catalog/{entry_id}/review",
    response_model=MCPCatalogReviewRead,
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
    return MCPCatalogReviewRead(
        id=entry.id,
        trust_status=entry.trust_status,
        verification_source=entry.verification_source,
    )


@router.get("/servers/{server_id}/inspector", response_model=MCPInspectorRead)
def inspector(
    server_id: uuid.UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
):
    from collections import Counter

    from app.integrations.models.mcp_server import MCPEvent, MCPOAuthToken

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
    events = (
        session.execute(
            select(MCPEvent)
            .where(MCPEvent.server_id == server.id)
            .order_by(MCPEvent.sequence.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
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
            {key: payload[key] for key in safe_payload_keys if key in payload}
            | {
                "event_type": event.event_type,
                "sequence": event.sequence,
                "created_at": event.created_at.isoformat(),
            }
        )
    config = server.config if isinstance(server.config, dict) else {}
    cached_tools = (
        config.get("mcp_tools_cache") if isinstance(config.get("mcp_tools_cache"), list) else []
    )
    return {
        "server": MCPServerRead.model_validate(server).model_dump(mode="json"),
        "diagnostics": {
            "credential_configured": session.execute(
                select(MCPOAuthToken.id).where(
                    MCPOAuthToken.server_id == server.id,
                    MCPOAuthToken.tenant_id == auth.tenant_id,
                    MCPOAuthToken.user_id == auth.user_id,
                )
            ).scalar_one_or_none()
            is not None,
            "oauth_configured": str(config.get("oauth_mode") or "none").lower() != "none"
            and session.execute(
                select(MCPOAuthToken.id).where(
                    MCPOAuthToken.server_id == server.id,
                    MCPOAuthToken.tenant_id == auth.tenant_id,
                    MCPOAuthToken.user_id == auth.user_id,
                )
            ).scalar_one_or_none()
            is not None,
            "catalog_counts": {
                key.removeprefix("mcp_").removesuffix("_cache"): len(value)
                for key, value in config.items()
                if key.startswith("mcp_") and key.endswith("_cache") and isinstance(value, list)
            },
            "event_counts": dict(Counter(event.event_type for event in events)),
            "latest_event": event_items[0] if event_items else None,
            "reconnect_attempts": int(server.reconnect_attempts or 0),
            "last_error": "MCP connection failed" if server.last_error else None,
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
