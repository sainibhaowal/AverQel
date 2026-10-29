from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.permissions import PERMISSIONS_BY_ROLE as PERMISSIONS_BY_ROLE
from app.auth.permissions import resolve_permissions as resolve_permissions
from app.auth.roles import canonicalize_role_name
from app.core.errors import ApiError


def require_permissions(
    *required_permissions: str,
) -> Callable[..., Awaitable[AuthContext]]:
    """
    Require one or more permissions for an endpoint dependency.
    """
    normalized_required = frozenset(canonicalize_role_name(p) for p in required_permissions)

    async def dependency(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not normalized_required:
            return auth
        missing = normalized_required - auth.permissions
        if missing:
            raise ApiError(
                code="FORBIDDEN",
                message="Insufficient permissions for requested operation.",
                status_code=403,
                details={"missing_permissions": sorted(missing)},
            )
        return auth

    return dependency
