from __future__ import annotations

import logging
import uuid
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Final, Protocol, cast

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, ImmatureSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.context import set_tenant_id, set_user_id
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.auth.roles import canonicalize_role_name
from app.db.session import get_db

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

ACCESS_TOKEN_TYPE: Final[str] = "access"
API_KEY_PREFIX: Final[str] = "dx_"
JWT_LEEWAY_SECONDS: Final[int] = 5


# ---------------------------------------------------------------------------
# Typed contracts
# ---------------------------------------------------------------------------


class ApiKeyRecord(Protocol):
    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    scopes: str | None
    expires_at: datetime | None
    revoked_at: datetime | None
    is_active: bool


class UserRecord(Protocol):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    is_active: bool
    roles: list[str] | set[str] | tuple[str, ...]
    access_token_version: int


class TenantRecord(Protocol):
    id: uuid.UUID


@dataclass(slots=True, frozen=True)
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    roles: frozenset[str]
    token_id: str
    permissions: frozenset[str] = frozenset()
    auth_type: str = "jwt"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _parse_uuid(
    value: Any,
    *,
    field_name: str,
    invalid_token_status: bool = True,
) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ApiError(
            code=(
                "INVALID_ACCESS_TOKEN" if invalid_token_status else "INVALID_TENANT_ID"
            ),
            message=f"{field_name} must be a valid UUID.",
            status_code=401 if invalid_token_status else 400,
        ) from exc


def _parse_requested_tenant_id(x_tenant_id: str | None) -> uuid.UUID | None:
    if x_tenant_id is None:
        return None
    return _parse_uuid(
        x_tenant_id,
        field_name="X-Tenant-Id",
        invalid_token_status=False,
    )


def _normalize_roles(raw_roles: Any) -> frozenset[str]:
    if raw_roles is None:
        return frozenset()

    if not isinstance(raw_roles, list):
        raise ApiError(
            code="INVALID_ACCESS_TOKEN",
            message="Access token role claims are invalid.",
            status_code=401,
        )

    normalized = {
        canonicalize_role_name(str(role)) for role in raw_roles if str(role).strip()
    }
    return frozenset(normalized)


def _normalize_permissions(raw_scopes: str | None) -> frozenset[str]:
    if not raw_scopes:
        return frozenset()
    return frozenset(part.strip() for part in raw_scopes.split(",") if part.strip())


def _enforce_tenant_scope(
    *,
    requested_tenant_id: uuid.UUID | None,
    actual_tenant_id: uuid.UUID,
) -> None:
    if requested_tenant_id is None:
        return

    if requested_tenant_id != actual_tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="Authenticated tenant scope does not match requested tenant.",
            status_code=403,
        )


def _bind_request_identity(*, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    set_tenant_id(str(tenant_id))
    set_user_id(str(user_id))


def _audit_auth_event(
    *,
    event: str,
    user_id: str | None = None,
    tenant_id: str | None = None,
    token_id: str | None = None,
    auth_type: str | None = None,
    outcome: str,
    reason: str | None = None,
) -> None:
    logger.info(
        "auth_event",
        extra={
            "event": event,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "token_id": token_id,
            "auth_type": auth_type,
            "outcome": outcome,
            "reason": reason,
        },
    )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _build_access_claims(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    roles: AbstractSet[str],
    access_token_version: int = 0,
    settings: Settings,
) -> dict[str, Any]:
    now = _utcnow()
    expires_at = now + timedelta(minutes=settings.jwt_access_ttl_minutes)

    return {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "roles": sorted(canonicalize_role_name(role) for role in roles if role.strip()),
        "jti": str(generate_uuid7_with_fallback()),
        "typ": ACCESS_TOKEN_TYPE,
        "ver": int(access_token_version),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    roles: AbstractSet[str],
    access_token_version: int = 0,
    settings: Settings,
) -> str:
    claims = _build_access_claims(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        access_token_version=access_token_version,
        settings=settings,
    )
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=JWT_LEEWAY_SECONDS,
            options={
                "require": [
                    "sub",
                    "tenant_id",
                    "jti",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                ],
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
            },
        )
        token_type = claims.get("typ")
        if token_type not in {None, ACCESS_TOKEN_TYPE}:
            raise ApiError(
                code="INVALID_ACCESS_TOKEN",
                message="Access token type is invalid.",
                status_code=401,
            )
    except ExpiredSignatureError as exc:
        raise ApiError(
            code="ACCESS_TOKEN_EXPIRED",
            message="Access token is expired.",
            status_code=401,
        ) from exc
    except ImmatureSignatureError as exc:
        raise ApiError(
            code="ACCESS_TOKEN_NOT_YET_VALID",
            message="Access token is not yet valid.",
            status_code=401,
        ) from exc
    except InvalidTokenError as exc:
        raise ApiError(
            code="INVALID_ACCESS_TOKEN",
            message="Access token is invalid.",
            status_code=401,
        ) from exc

    if str(claims.get("typ", "")).strip() != ACCESS_TOKEN_TYPE:
        raise ApiError(
            code="INVALID_ACCESS_TOKEN",
            message="Token type is invalid for this endpoint.",
            status_code=401,
        )

    return claims


# ---------------------------------------------------------------------------
# DB-backed state validation
# ---------------------------------------------------------------------------


def _validate_live_user_and_tenant(
    *,
    db: Session,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[UserRecord, TenantRecord]:
    from app.auth.repositories.tenants import TenantsRepository
    from app.auth.repositories.users import UsersRepository

    user_repo = UsersRepository(db)
    tenant_repo = TenantsRepository(db)

    user = cast(
        UserRecord | None,
        user_repo.get_by_id(tenant_id=tenant_id, user_id=user_id),
    )
    if user is None or not user.is_active:
        raise ApiError(
            code="USER_DISABLED",
            message="User account is inactive.",
            status_code=401,
        )

    tenant = cast(TenantRecord | None, tenant_repo.get_by_id(tenant_id=tenant_id))
    tenant_is_active = (
        bool(getattr(tenant, "is_active", True)) if tenant is not None else False
    )
    if tenant is None or not tenant_is_active:
        raise ApiError(
            code="TENANT_DISABLED",
            message="Tenant is inactive.",
            status_code=403,
        )

    if user.tenant_id != tenant_id:
        raise ApiError(
            code="TENANT_SCOPE_MISMATCH",
            message="User tenant membership is invalid.",
            status_code=403,
        )

    return user, tenant


def _load_live_role_names(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> frozenset[str]:
    from app.auth.repositories.roles import RolesRepository

    role_names = RolesRepository(db).get_role_names_for_user(tenant_id, user_id)
    return frozenset(
        canonicalize_role_name(str(role)) for role in role_names if str(role).strip()
    )


def _enforce_platform_admin_allowlist(
    *,
    roles: frozenset[str],
    user: UserRecord,
    settings: Settings,
) -> frozenset[str]:
    return roles


def _check_jwt_not_revoked(*, db: Session, tenant_id: uuid.UUID, token_id: str) -> None:
    """Check access-token revocation using Redis as a cache and the database as source of truth."""
    revoked = False
    try:
        from app.system.services.cache_service import get_redis_client  # noqa: PLC0415

        rc = get_redis_client()
        revoked = bool(rc.exists(f"jwt:deny:{token_id}"))
    except Exception:  # noqa: BLE001
        logger.warning(
            "JWT denylist cache check failed; falling back to database.", exc_info=True
        )

    if not revoked:
        from app.auth.repositories.revoked_access_tokens import (
            RevokedAccessTokensRepository,
        )

        revoked = RevokedAccessTokensRepository(db).exists(
            tenant_id=tenant_id,
            token_id=token_id,
        )

    if revoked:
        raise ApiError(
            code="TOKEN_REVOKED",
            message="Access token has been revoked. Please log in again.",
            status_code=401,
        )


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def build_auth_context_from_jwt(
    *,
    claims: dict[str, Any],
    x_tenant_id: str | None,
    db: Session,
) -> AuthContext:
    try:
        user_id = _parse_uuid(claims["sub"], field_name="sub")
        tenant_id = _parse_uuid(claims["tenant_id"], field_name="tenant_id")
        token_id = str(claims["jti"]).strip()
        token_version = int(claims.get("ver", 0))
        if not token_id:
            raise ValueError("Missing jti")
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            code="INVALID_ACCESS_TOKEN",
            message="Access token does not include required claims.",
            status_code=401,
        ) from exc

    requested_tenant_id = _parse_requested_tenant_id(x_tenant_id)
    _enforce_tenant_scope(
        requested_tenant_id=requested_tenant_id,
        actual_tenant_id=tenant_id,
    )

    _check_jwt_not_revoked(db=db, tenant_id=tenant_id, token_id=token_id)
    live_user, _live_tenant = _validate_live_user_and_tenant(
        db=db,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    if token_version != int(live_user.access_token_version):
        raise ApiError(
            code="TOKEN_REVOKED",
            message="Access token has been invalidated. Please log in again.",
            status_code=401,
        )

    token_roles = _normalize_roles(claims.get("roles"))
    db_roles = _load_live_role_names(db=db, tenant_id=tenant_id, user_id=user_id)
    effective_roles = token_roles & db_roles if token_roles else db_roles
    if not effective_roles and token_roles:
        effective_roles = token_roles
    effective_roles = _enforce_platform_admin_allowlist(
        roles=effective_roles,
        user=live_user,
        settings=get_settings(),
    )

    _bind_request_identity(tenant_id=tenant_id, user_id=user_id)

    _audit_auth_event(
        event="jwt_auth",
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        token_id=token_id,
        auth_type="jwt",
        outcome="success",
    )

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=effective_roles,
        permissions=frozenset(),
        token_id=token_id,
        auth_type="jwt",
    )


def build_auth_context_from_api_key(
    *,
    api_key: ApiKeyRecord,
    requested_tenant_id: uuid.UUID | None,
    db: Session,
) -> AuthContext:
    if not api_key.is_active or api_key.revoked_at is not None:
        raise ApiError(
            code="INVALID_API_KEY",
            message="API key is invalid or revoked.",
            status_code=401,
        )

    if api_key.expires_at and api_key.expires_at < _utcnow():
        raise ApiError(
            code="EXPIRED_API_KEY",
            message="API key is expired.",
            status_code=401,
        )

    _enforce_tenant_scope(
        requested_tenant_id=requested_tenant_id,
        actual_tenant_id=api_key.tenant_id,
    )

    _validate_live_user_and_tenant(
        db=db,
        user_id=api_key.user_id,
        tenant_id=api_key.tenant_id,
    )

    _bind_request_identity(tenant_id=api_key.tenant_id, user_id=api_key.user_id)

    _audit_auth_event(
        event="api_key_auth",
        user_id=str(api_key.user_id),
        tenant_id=str(api_key.tenant_id),
        token_id=f"apikey_{api_key.id}",
        auth_type="api_key",
        outcome="success",
    )

    return AuthContext(
        user_id=api_key.user_id,
        tenant_id=api_key.tenant_id,
        roles=frozenset(),
        permissions=_normalize_permissions(api_key.scopes),
        token_id=f"apikey_{api_key.id}",
        auth_type="api_key",
    )


def build_auth_context(
    claims: dict[str, Any],
    x_tenant_id: str | None,
) -> AuthContext:
    """
    Backward-compatible auth-context builder for unit tests and legacy call sites.

    Runtime request auth should continue to use the DB-backed JWT/API-key flows.
    """
    user_id = _parse_uuid(claims.get("sub"), field_name="sub")
    tenant_id = _parse_uuid(claims.get("tenant_id"), field_name="tenant_id")
    token_id = _parse_uuid(claims.get("jti"), field_name="jti")
    roles = _normalize_roles(claims.get("roles"))
    requested_tenant_id = _parse_requested_tenant_id(x_tenant_id)

    _enforce_tenant_scope(
        requested_tenant_id=requested_tenant_id,
        actual_tenant_id=tenant_id,
    )

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        permissions=frozenset(),
        token_id=str(token_id),
        auth_type="jwt",
    )


# ---------------------------------------------------------------------------
# Public dependency
# ---------------------------------------------------------------------------


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        _audit_auth_event(
            event="auth_missing",
            outcome="failure",
            reason="missing_or_invalid_bearer_scheme",
        )
        raise ApiError(
            code="AUTH_REQUIRED",
            message="Bearer access token or API key is required.",
            status_code=401,
        )

    token = credentials.credentials.strip()
    if not token:
        _audit_auth_event(
            event="auth_missing",
            outcome="failure",
            reason="empty_bearer_token",
        )
        raise ApiError(
            code="AUTH_REQUIRED",
            message="Bearer access token or API key is required.",
            status_code=401,
        )

    requested_tenant_id = _parse_requested_tenant_id(x_tenant_id)

    if token.startswith(API_KEY_PREFIX):
        from app.auth.repositories.api_keys import ApiKeysRepository

        repo = ApiKeysRepository(db)
        key_hash = repo.hash_key(token)
        api_key = cast(ApiKeyRecord | None, repo.get_by_hash(key_hash=key_hash))

        if api_key is None:
            _audit_auth_event(
                event="api_key_auth",
                auth_type="api_key",
                outcome="failure",
                reason="invalid_api_key",
            )
            raise ApiError(
                code="INVALID_API_KEY",
                message="API key is invalid or revoked.",
                status_code=401,
            )

        return build_auth_context_from_api_key(
            api_key=api_key,
            requested_tenant_id=requested_tenant_id,
            db=db,
        )

    claims = decode_access_token(token, settings)

    try:
        return build_auth_context_from_jwt(
            claims=claims,
            x_tenant_id=x_tenant_id,
            db=db,
        )
    except ApiError as exc:
        token_id = str(claims.get("jti", "")).strip() or None
        user_id = str(claims.get("sub", "")).strip() or None
        tenant_id = str(claims.get("tenant_id", "")).strip() or None
        _audit_auth_event(
            event="jwt_auth",
            user_id=user_id,
            tenant_id=tenant_id,
            token_id=token_id,
            auth_type="jwt",
            outcome="failure",
            reason=exc.code,
        )
        raise


AUTH_CONTEXT_DEPENDENCY = Depends(get_auth_context)
