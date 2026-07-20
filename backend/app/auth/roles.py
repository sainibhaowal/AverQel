from __future__ import annotations

from typing import Final

ROLE_ALIASES: Final[dict[str, str]] = {
    "reader": "user",
    "super_admin": "admin",
}


def canonicalize_role_name(role: str) -> str:
    normalized = role.strip().lower()
    return ROLE_ALIASES.get(normalized, normalized)


def canonicalize_role_names(
    roles: list[str] | set[str] | tuple[str, ...] | frozenset[str],
) -> frozenset[str]:
    return frozenset(
        canonicalize_role_name(role)
        for role in roles
        if isinstance(role, str) and role.strip()
    )


def is_admin_role(
    roles: list[str] | set[str] | tuple[str, ...] | frozenset[str],
) -> bool:
    return "admin" in canonicalize_role_names(roles)


def is_platform_admin_email(
    email: str,
    allowed_emails: list[str] | set[str] | tuple[str, ...] | frozenset[str],
) -> bool:
    normalized_email = email.strip().lower()
    if not normalized_email:
        return False
    return normalized_email in {
        allowed.strip().lower()
        for allowed in allowed_emails
        if isinstance(allowed, str) and allowed.strip()
    }
