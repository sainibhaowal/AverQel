from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.errors import ApiError
from app.platform.database.session import get_db, set_db_tenant_context


@dataclass(slots=True, frozen=True)
class TenantContext:
    """Authenticated tenant context bound to the current request."""

    tenant_id: uuid.UUID
    user_id: uuid.UUID


def apply_tenant_context(db: Session, tenant_id: uuid.UUID) -> None:
    """Apply tenant scoping to the database session."""
    set_db_tenant_context(db, tenant_id)


def get_tenant_context(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Resolve and apply tenant context from authenticated request identity."""
    apply_tenant_context(db, auth.tenant_id)
    return TenantContext(tenant_id=auth.tenant_id, user_id=auth.user_id)


def _parse_tenant_header(
    x_tenant_id: str | None,
    *,
    required_message: str | None = None,
) -> uuid.UUID | None:
    """Parse the X-Tenant-Id header into a UUID."""
    if x_tenant_id is None:
        if required_message is not None:
            raise ApiError(
                code="TENANT_REQUIRED",
                message=required_message,
                status_code=400,
            )
        return None

    cleaned = x_tenant_id.strip()
    if not cleaned:
        if required_message is not None:
            raise ApiError(
                code="TENANT_REQUIRED",
                message=required_message,
                status_code=400,
            )
        return None

    try:
        return uuid.UUID(cleaned)
    except ValueError as exc:
        raise ApiError(
            code="INVALID_TENANT_ID",
            message="X-Tenant-Id must be a valid UUID.",
            status_code=400,
        ) from exc


def get_login_tenant_id(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> uuid.UUID | None:
    """Return optional tenant id for login flows."""
    return _parse_tenant_header(x_tenant_id)


def require_login_tenant_id(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> uuid.UUID:
    """Require tenant id for login flows."""
    tenant_id = _parse_tenant_header(
        x_tenant_id,
        required_message="X-Tenant-Id header is required for login.",
    )
    if tenant_id is None:
        raise RuntimeError(
            "tenant id parser returned None for a required login tenant id"
        )
    return tenant_id


def require_request_tenant_id(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> uuid.UUID:
    """Require tenant id for request flows that must be explicitly tenant-scoped."""
    tenant_id = _parse_tenant_header(
        x_tenant_id,
        required_message="X-Tenant-Id header is required.",
    )
    if tenant_id is None:
        raise RuntimeError(
            "tenant id parser returned None for a required request tenant id"
        )
    return tenant_id
