from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.permissions import PERMISSIONS_BY_ROLE as PERMISSIONS_BY_ROLE
from app.auth.permissions import resolve_permissions as resolve_permissions
from app.core.errors import ApiError

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
        missing = [permission for permission in normalized_required if permission not in granted]
        if missing:
            raise ApiError(
                code="FORBIDDEN",
                message="Insufficient permissions for requested operation.",
                status_code=403,
                details={"missing_permissions": missing},
            )
        return auth

    return dependency
