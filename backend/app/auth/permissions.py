from __future__ import annotations

from typing import Final

from app.auth.roles import canonicalize_role_name

PERMISSIONS_BY_ROLE: Final[dict[str, frozenset[str]]] = {
    "admin": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
            "documents:upload",
            "documents:read",
            "documents:delete",
            "documents:organization:basic",
            "documents:organization:advanced",
            "documents:organization:admin",
            "collections:read",
            "collections:write",
            "queries:run",
            "deepspace:diagnostics",
            "providers:read",
            "providers:write",
            "providers:test",
            "providers:assign",
            "providers:oauth",
            "admin:audit_logs:read",
            "admin:break_glass:write",
            "admin:data_deletions:write",
            "admin:data_deletions:approve",
            "admin:data_deletions:read",
            "admin:support:read",
            "admin:support:write",
            "admin:feedback:read",
            "admin:feedback:write",
            "admin:metrics:read",
            "admin:users:read",
            "admin:users:disable",
            "admin:users:reactivate",
            "admin:users:logout",
            "admin:users:delete",
            "mcp:catalog:manage",
        }
    ),
    # Legacy support/feedback manager assignments no longer grant access to
    # cross-tenant customer content. Only the allowlisted platform-admin path
    # can enter those queues.
    "support_manager": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
        }
    ),
    "feedback_manager": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
        }
    ),
    "collection_moderator": frozenset(
        {
            "auth:login_self",
            "auth:refresh_self",
            "auth:logout_self",
            "collections:moderation:read",
            "collections:moderation:write",
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
            "documents:organization:basic",
            "documents:organization:advanced",
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
            "documents:organization:basic",
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
