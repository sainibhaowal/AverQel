from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Depends

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.roles import canonicalize_role_name
from app.core.errors import ApiError

PERMISSIONS_BY_ROLE: Final[dict[str, frozenset[str]]] = {
    "admin": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
            "documents:upload",
            "documents:read",
            "documents:delete",
            "collections:read",
            "collections:write",
            "queries:run",
            "deepspace:diagnostics",
            "providers:read",
            "providers:write",
            "providers:test",
            "providers:assign",
            "providers:oauth",
            "admin:analytics:read",
            "admin:audit_logs:read",
            "admin:collections:read",
            "admin:collections:write",
            "admin:data_deletions:write",
            "admin:data_deletions:read",
            "admin:metrics:read",
            "admin:users:read",
            "admin:users:write",
            "admin:support:read",
            "admin:support:write",
            "admin:feedback:read",
            "admin:feedback:write",
            "mcp:catalog:manage",
        }
    ),
    "editor": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
            "documents:upload",
            "documents:read",
            "documents:delete",
            "collections:read",
            "collections:write",
            "queries:run",
            "providers:read",
            "providers:write",
            "providers:test",
            "providers:assign",
            "providers:oauth",
        }
    ),
    "user": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
            # Free users and paid editors have the same normal workspace
            # capabilities. Admin-only controls remain separate admin:* permissions.
            "documents:upload",
            "documents:read",
            "documents:delete",
            "collections:read",
            "collections:write",
            "queries:run",
            "providers:read",
            "providers:write",
            "providers:test",
            "providers:assign",
            "providers:oauth",
        }
    ),
    "service": frozenset(
        {
            "documents:upload",
            "documents:read",
            "queries:run",
        }
    ),
}

PERMISSIONS_BY_ROLE["super_admin"] = PERMISSIONS_BY_ROLE["admin"]
PERMISSIONS_BY_ROLE["reader"] = PERMISSIONS_BY_ROLE["user"]
PERMISSIONS_BY_ROLE["member"] = PERMISSIONS_BY_ROLE["user"]

AUTH_CONTEXT_DEPENDENCY = Depends(get_auth_context)


def _normalize_permissions(values: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize required permissions while preserving order."""
    seen: set[str] = set()
    normalized: list[str] = []

    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return tuple(normalized)


def resolve_permissions(
    *,
    roles: frozenset[str],
    direct_permissions: frozenset[str] | None = None,
) -> frozenset[str]:
    """
    Resolve effective permissions from role-derived permissions plus optional
    directly granted permissions.
    """
    permissions: set[str] = set()

    for role in roles:
        permissions.update(PERMISSIONS_BY_ROLE.get(canonicalize_role_name(role), frozenset()))

    if direct_permissions:
        permissions.update(direct_permissions)

    return frozenset(permissions)


def require_permissions(
    *required_permissions: str,
) -> Callable[..., Awaitable[AuthContext]]:
    """
    Require one or more permissions for an endpoint dependency.
    """
    normalized_required = _normalize_permissions(required_permissions)

    async def dependency(auth: AuthContext = AUTH_CONTEXT_DEPENDENCY) -> AuthContext:
        if not normalized_required:
            return auth

        granted = resolve_permissions(
            roles=frozenset(auth.roles),
            direct_permissions=getattr(auth, "permissions", frozenset()),
        )

        missing = [perm for perm in normalized_required if perm not in granted]
        if missing:
            raise ApiError(
                code="FORBIDDEN",
                message="Insufficient permissions for requested operation.",
                status_code=403,
                details={"missing_permissions": missing},
            )

        return auth

    return dependency
