from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.auth.rbac import require_permissions
from app.auth.tenancy import get_login_tenant_id
from app.db.session import get_db
from app.auth.schemas.auth import (
    AccountActivityItem,
    AccountActivityResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    CookiePreferencesRequest,
    CookiePreferencesResponse,
    DeleteAccountRequest,
    DeleteAccountResponse,
    ExportAccountResponse,
    LoginRequest,
    LogoutResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RefreshResponse,
    RegisterRequest,
    TokenResponse,
    TotpConfirmRequest,
    TotpConfirmResponse,
    TotpDisableRequest,
    TotpSetupResponse,
    TotpVerifyRequest,
    UserRegisterResponse,
)
from app.auth.services.auth_service import AuthService
from app.services.system.audit_service import AuditService
from app.services.system.rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(
    response: Response, settings: Settings, refresh_token: str
) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
    )


def _audit_and_commit(
    *,
    db: Session,
    tenant_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None,
    details: dict[str, str] | None = None,
) -> None:
    try:
        AuditService(db).write_event(
            tenant_id=tenant_id,
            action=action,
            resource_type="auth",
            actor_user_id=actor_user_id,
            details=details or {},
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning(
            "Failed to persist auth audit event.",
            extra={
                "tenant_id": str(tenant_id),
                "actor_user_id": str(actor_user_id) if actor_user_id else None,
                "action": action,
            },
            exc_info=True,
        )


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    tenant_id: uuid.UUID | None = Depends(get_login_tenant_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    limiter = RateLimitService(settings)
    limiter.enforce_auth_login_limit(
        request=request,
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        email=payload.email,
    )

    service = AuthService(db, settings)
    result = service.login(
        tenant_id=tenant_id,
        email=payload.email,
        password=payload.password,
    )

    _audit_and_commit(
        db=db,
        tenant_id=result.user.tenant_id,
        action="auth.login",
        actor_user_id=result.user.id,
        details={"email": payload.email},
    )

    if result.requires_2fa:
        return TokenResponse(
            access_token="",
            token_type="bearer",  # nosec B106
            expires_in=0,
            user=AuthUserResponse(
                user_id=str(result.user.id),
                tenant_id=str(result.user.tenant_id),
                roles=[role for role in result.roles if role],
            ),
            requires_2fa=True,
            pending_token=result.pending_token,
        )

    _set_refresh_cookie(response, settings, result.refresh_token)

    return TokenResponse(
        access_token=result.access_token,
        token_type="bearer",  # nosec B106 - OAuth token type constant, not a secret
        expires_in=result.expires_in,
        user=AuthUserResponse(
            user_id=str(result.user.id),
            tenant_id=str(result.user.tenant_id),
            roles=[role for role in result.roles if role],
        ),
    )


@router.post("/register", response_model=UserRegisterResponse)
def register(
    request: Request,
    payload: RegisterRequest,
    tenant_id: uuid.UUID | None = Depends(get_login_tenant_id),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserRegisterResponse:
    limiter = RateLimitService(settings)
    limiter.enforce_auth_login_limit(
        request=request,
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        email=payload.email,
    )

    service = AuthService(db, settings)
    user = service.register(
        tenant_id=tenant_id,
        email=payload.email,
        password=payload.password,
    )

    _audit_and_commit(
        db=db,
        tenant_id=user.tenant_id,
        action="auth.register",
        actor_user_id=user.id,
        details={"email": payload.email},
    )

    return UserRegisterResponse(
        user_id=str(user.id),
        email=user.email,
        status="active",
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RefreshResponse:
    limiter = RateLimitService(settings)
    limiter.enforce_auth_refresh_limit(request=request)

    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh_token is None:
        raise ApiError(
            code="REFRESH_TOKEN_REQUIRED",
            message="Refresh token cookie is required.",
            status_code=401,
        )

    service = AuthService(db, settings)
    result = service.refresh(raw_refresh_token=raw_refresh_token)

    # Audit against the refreshed user/tenant from service result if available.
    refreshed_user = getattr(result, "user", None)
    refreshed_tenant_id = getattr(refreshed_user, "tenant_id", None)
    refreshed_user_id = getattr(refreshed_user, "id", None)
    if refreshed_tenant_id is not None:
        _audit_and_commit(
            db=db,
            tenant_id=refreshed_tenant_id,
            action="auth.refresh",
            actor_user_id=refreshed_user_id,
        )

    _set_refresh_cookie(response, settings, result.refresh_token)

    return RefreshResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
    dependencies=[Depends(require_permissions("auth:logout_self"))],
)
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    limiter = RateLimitService(settings)
    limiter.enforce_auth_logout_limit(
        request=request,
        user_id=str(auth.user_id),
    )

    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    service = AuthService(db, settings)
    service.logout(auth=auth, raw_refresh_token=raw_refresh_token)

    _audit_and_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="auth.logout",
        actor_user_id=auth.user_id,
    )

    _clear_refresh_cookie(response, settings)
    return LogoutResponse(success=True)


@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    service = AuthService(db, settings)
    user = service.users.get_by_id(auth.tenant_id, auth.user_id)
    if user is None:
        raise ApiError(
            code="USER_NOT_FOUND",
            message="User not found.",
            status_code=404,
        )

    return ProfileResponse(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        collection_code=user.collection_code,
        email=user.email,
        roles=sorted(list(auth.roles)),
        status="active" if user.is_active else "locked",
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        totp_enabled=user.totp_enabled,
        avatar=user.avatar,
    )


@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    service = AuthService(db, settings)
    user = service.users.get_by_id(auth.tenant_id, auth.user_id)
    if user is None:
        raise ApiError(
            code="USER_NOT_FOUND",
            message="User not found.",
            status_code=404,
        )

    if payload.avatar is not None:
        user.avatar = payload.avatar
        db.commit()

    return ProfileResponse(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
        collection_code=user.collection_code,
        email=user.email,
        roles=sorted(list(auth.roles)),
        status="active" if user.is_active else "locked",
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        totp_enabled=user.totp_enabled,
        avatar=user.avatar,
    )


@router.get(
    "/activity",
    response_model=AccountActivityResponse,
    dependencies=[Depends(require_permissions("auth:login_self"))],
)
def get_account_activity(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountActivityResponse:
    items = AuthService(db, settings).get_account_activity(auth=auth, limit=100)
    return AccountActivityResponse(
        items=[
            AccountActivityItem(
                id=str(item.id),
                action=item.action,
                status=item.status,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                created_at=item.created_at,
                details={str(k): str(v) for k, v in (item.details or {}).items()},
            )
            for item in items
        ]
    )


@router.get(
    "/export",
    response_model=ExportAccountResponse,
    dependencies=[Depends(require_permissions("auth:login_self"))],
)
def export_account_data(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ExportAccountResponse:
    payload = AuthService(db, settings).export_account_data(auth=auth)
    recent_activity = payload["recent_activity"]
    return ExportAccountResponse(
        generated_at=datetime.now(tz=UTC),
        account=cast(dict[str, object], payload["account"]),
        workspace_counts=payload["workspace_counts"],
        recent_activity=[
            AccountActivityItem(
                id=str(item.id),
                action=item.action,
                status=item.status,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                created_at=item.created_at,
                details={str(k): str(v) for k, v in (item.details or {}).items()},
            )
            for item in recent_activity
        ],
    )


@router.delete(
    "/account",
    response_model=DeleteAccountResponse,
    dependencies=[Depends(require_permissions("auth:logout_self"))],
)
def delete_own_account(
    request: Request,
    response: Response,
    payload: DeleteAccountRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeleteAccountResponse:
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    AuthService(db, settings).delete_own_account(
        auth=auth,
        raw_refresh_token=raw_refresh_token,
        password=payload.password,
    )
    _clear_refresh_cookie(response, settings)
    return DeleteAccountResponse(success=True)


@router.post(
    "/cookie-preferences",
    response_model=CookiePreferencesResponse,
    dependencies=[Depends(require_permissions("auth:login_self"))],
)
def save_cookie_preferences(
    payload: CookiePreferencesRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CookiePreferencesResponse:
    AuthService(db, settings).save_cookie_preferences(
        auth=auth,
        essential=payload.essential,
        analytics=payload.analytics,
        marketing=payload.marketing,
    )
    return CookiePreferencesResponse(success=True)


@router.post("/change-password", response_model=LogoutResponse)
def change_password(
    payload: ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    service = AuthService(db, settings)
    service.change_password(
        auth=auth,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )

    _audit_and_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="auth.password_change",
        actor_user_id=auth.user_id,
    )

    return LogoutResponse(success=True)


# ------------------------------------------------------------------
# Logout all devices
# ------------------------------------------------------------------


@router.post(
    "/logout-all",
    response_model=LogoutResponse,
    dependencies=[Depends(require_permissions("auth:logout_self"))],
)
def logout_all(
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    service = AuthService(db, settings)
    service.logout_all(auth=auth)

    _audit_and_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="auth.logout_all",
        actor_user_id=auth.user_id,
    )

    _clear_refresh_cookie(response, settings)
    return LogoutResponse(success=True)


# ------------------------------------------------------------------
# 2FA endpoints
# ------------------------------------------------------------------


@router.post("/2fa/verify", response_model=TokenResponse)
def verify_2fa(
    request: Request,
    payload: TotpVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    limiter = RateLimitService(settings)
    limiter.enforce_auth_login_limit(
        request=request, tenant_id=None, email="2fa_verify"
    )

    service = AuthService(db, settings)
    result = service.verify_totp_login(
        pending_token=payload.pending_token,
        code=payload.code,
    )

    _audit_and_commit(
        db=db,
        tenant_id=result.user.tenant_id,
        action="auth.2fa_verify",
        actor_user_id=result.user.id,
    )

    _set_refresh_cookie(response, settings, result.refresh_token)

    return TokenResponse(
        access_token=result.access_token,
        token_type="bearer",  # nosec B106
        expires_in=result.expires_in,
        user=AuthUserResponse(
            user_id=str(result.user.id),
            tenant_id=str(result.user.tenant_id),
            roles=[role for role in result.roles if role],
        ),
    )


@router.post("/2fa/setup", response_model=TotpSetupResponse)
def setup_2fa(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TotpSetupResponse:
    service = AuthService(db, settings)
    result = service.setup_totp(auth=auth)

    _audit_and_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="auth.2fa_setup",
        actor_user_id=auth.user_id,
    )

    return TotpSetupResponse(
        secret=result.secret,
        provisioning_uri=result.provisioning_uri,
    )


@router.post("/2fa/confirm", response_model=TotpConfirmResponse)
def confirm_2fa(
    payload: TotpConfirmRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TotpConfirmResponse:
    service = AuthService(db, settings)
    backup_codes = service.confirm_totp(auth=auth, code=payload.code)

    _audit_and_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="auth.2fa_enabled",
        actor_user_id=auth.user_id,
    )

    return TotpConfirmResponse(backup_codes=backup_codes)


@router.post(
    "/2fa/disable",
    response_model=LogoutResponse,
)
def disable_2fa(
    payload: TotpDisableRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    service = AuthService(db, settings)
    service.disable_totp(auth=auth, password=payload.password)

    _audit_and_commit(
        db=db,
        tenant_id=auth.tenant_id,
        action="auth.2fa_disabled",
        actor_user_id=auth.user_id,
    )

    return LogoutResponse(success=True)
