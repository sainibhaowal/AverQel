from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

import pyotp
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, create_access_token
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.auth.roles import canonicalize_role_names, is_platform_admin_email
from app.auth.security import (
    generate_secure_token,
    hash_password,
    hash_refresh_token,
    validate_password_policy,
    verify_password,
)
from app.auth.models.refresh_token import RefreshToken
from app.auth.models.revoked_access_token import RevokedAccessToken
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.documents.models.collection import CollectionPermission
from app.documents.models.document import Document
from app.models.query.comment import Comment
from app.models.query.conversation import Conversation
from app.models.query.pinned_finding import PinnedFinding
from app.models.query.query import Query
from app.auth.repositories.refresh_tokens import RefreshTokensRepository
from app.auth.repositories.revoked_access_tokens import RevokedAccessTokensRepository
from app.auth.repositories.roles import RolesRepository
from app.auth.repositories.tenants import TenantsRepository
from app.auth.repositories.users import UsersRepository
from app.services.security.provider_secret_crypto import (
    ProviderSecretCrypto,
    ProviderSecretCryptoError,
)
from app.services.system.audit_service import AuditService
from app.services.system.storage_service import StorageService

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _generate_collection_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


logger = logging.getLogger(__name__)

_TOTP_BACKUP_CODE_COUNT = 8
_TOTP_BACKUP_CODE_LENGTH = 8  # hex chars → 4 bytes of randomness each


@dataclass(slots=True)
class LoginResult:
    user: User
    roles: list[str]
    requires_2fa: bool = False
    # Populated when requires_2fa is False:
    access_token: str = ""
    refresh_token: str = ""
    expires_in: int = 0
    # Populated when requires_2fa is True:
    pending_token: str = ""


@dataclass(slots=True)
class TotpSetupResult:
    secret: str
    provisioning_uri: str
    backup_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RefreshResult:
    access_token: str
    refresh_token: str
    expires_in: int


class ExportAccountData(TypedDict):
    user_id: str
    tenant_id: str
    email: str
    roles: list[str]
    status: str
    totp_enabled: bool
    created_at: datetime
    last_login_at: datetime | None


class ExportAccountPayload(TypedDict):
    account: ExportAccountData
    workspace_counts: dict[str, int]
    recent_activity: list[Any]


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.users = UsersRepository(db)
        self.roles = RolesRepository(db)
        self.tenants = TenantsRepository(db)
        self.refresh_tokens = RefreshTokensRepository(db)
        self.revoked_access_tokens = RevokedAccessTokensRepository(db)

    def login(
        self,
        *,
        tenant_id: uuid.UUID | None = None,
        email: str,
        password: str,
    ) -> LoginResult:
        normalized_email = email.strip().lower()
        if not normalized_email or not password:
            raise ApiError(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
                status_code=401,
            )

        user: User | None
        resolved_tenant_id = tenant_id

        if resolved_tenant_id is None:
            user = self.users.get_by_email_global(normalized_email)
            if user is not None:
                resolved_tenant_id = user.tenant_id
        else:
            user = self.users.get_by_email(resolved_tenant_id, normalized_email)

        if user is None or resolved_tenant_id is None:
            raise ApiError(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
                status_code=401,
            )

        self._ensure_bootstrap_admin_role(user=user)

        self._ensure_user_can_authenticate(user=user)

        if not verify_password(password, user.password_hash):
            self.users.register_failed_login(
                tenant_id=resolved_tenant_id,
                user=user,
                max_failed_attempts=self.settings.auth_max_failed_attempts,
                lockout_minutes=self.settings.auth_lockout_minutes,
            )
            self.db.commit()
            raise ApiError(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
                status_code=401,
            )

        role_names = self._effective_role_names_for_user(
            user=user,
            tenant_id=resolved_tenant_id,
        )
        if not role_names:
            raise ApiError(
                code="ROLE_ASSIGNMENT_REQUIRED",
                message="User has no assigned roles.",
                status_code=403,
            )

        self.users.register_successful_login(tenant_id=resolved_tenant_id, user=user)

        # If 2FA is enabled, return a short-lived pending token instead of full tokens.
        if user.totp_enabled:
            pending_token = self._mint_pending_2fa_token(
                user_id=user.id,
                tenant_id=resolved_tenant_id,
            )
            self.db.commit()
            return LoginResult(
                user=user,
                roles=sorted(role_names),
                requires_2fa=True,
                pending_token=pending_token,
            )

        access_token = create_access_token(
            user_id=user.id,
            tenant_id=resolved_tenant_id,
            roles=role_names,
            access_token_version=user.access_token_version,
            settings=self.settings,
        )

        raw_refresh_token = self._mint_refresh_token(tenant_id=resolved_tenant_id)
        hashed_refresh_token = hash_refresh_token(
            raw_refresh_token,
            self.settings.refresh_token_hash_secret,
        )
        refresh_token_row = RefreshToken(
            id=generate_uuid7_with_fallback(),
            tenant_id=resolved_tenant_id,
            user_id=user.id,
            token_hash=hashed_refresh_token,
            token_family_id=generate_uuid7_with_fallback(),
            expires_at=self._refresh_expiry(),
        )
        self.refresh_tokens.create(refresh_token_row)
        self.db.commit()

        return LoginResult(
            user=user,
            roles=sorted(role_names),
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=self.settings.jwt_access_ttl_minutes * 60,
        )

    def register(
        self,
        *,
        tenant_id: uuid.UUID | None = None,
        email: str,
        password: str,
    ) -> User:
        normalized_email = email.strip().lower()
        if not normalized_email or "@" not in normalized_email:
            raise ApiError(
                code="INVALID_EMAIL",
                message="Email format is invalid.",
                status_code=400,
            )
        if not password or not password.strip():
            raise ApiError(
                code="INVALID_PASSWORD",
                message="Password must not be empty.",
                status_code=400,
            )
        try:
            validate_password_policy(password)
        except ValueError as exc:
            raise ApiError(
                code="INVALID_PASSWORD",
                message=str(exc),
                status_code=400,
            ) from exc

        if self.users.get_by_email_global(normalized_email):
            raise ApiError(
                code="USER_ALREADY_EXISTS",
                message="A user with this email already exists in the system.",
                status_code=409,
            )

        now = datetime.now(tz=UTC)

        if tenant_id is None:
            tenant_id = generate_uuid7_with_fallback()
            new_tenant = Tenant(
                id=tenant_id,
                name=f"Workspace for {normalized_email}",
                created_at=now,
                updated_at=now,
            )
            self.tenants.create(new_tenant)
            self.db.flush()

        password_hash = hash_password(password)
        collection_code = _generate_collection_code()
        while self.users.get_by_collection_code_global(collection_code) is not None:
            collection_code = _generate_collection_code()

        user = User(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            email=normalized_email,
            collection_code=collection_code,
            password_hash=password_hash,
            is_active=True,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
        )
        self.users.create(user)

        self._assign_initial_role(user=user)

        self.db.commit()
        return user

    def _assign_initial_role(self, *, user: User) -> None:
        role_name = (
            "admin" if self._is_bootstrap_super_admin_email(user.email) else "user"
        )
        self._replace_user_roles(
            tenant_id=user.tenant_id, user_id=user.id, role_name=role_name
        )

    def _ensure_bootstrap_admin_role(self, *, user: User) -> None:
        if not self._is_bootstrap_super_admin_email(user.email):
            return

        current_roles = canonicalize_role_names(
            self.roles.get_role_names_for_user(user.tenant_id, user.id)
        )
        if current_roles == {"admin"}:
            return

        self._replace_user_roles(
            tenant_id=user.tenant_id,
            user_id=user.id,
            role_name="admin",
        )

    def _replace_user_roles(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role_name: str,
    ) -> None:
        role = self.roles.get_by_name(role_name)
        if role is None:
            raise ApiError(
                code="ROLE_ASSIGNMENT_REQUIRED",
                message=f"Required role '{role_name}' is not configured.",
                status_code=500,
            )

        self.db.execute(
            delete(UserRole).where(
                UserRole.tenant_id == tenant_id,
                UserRole.user_id == user_id,
            )
        )
        self.db.flush()
        self.db.add(
            UserRole(
                tenant_id=tenant_id,
                user_id=user_id,
                role_id=role.id,
            )
        )

    def _is_bootstrap_super_admin_email(self, email: str) -> bool:
        return is_platform_admin_email(
            email, self.settings.bootstrap_super_admin_emails
        )

    def change_password(
        self,
        *,
        auth: AuthContext,
        current_password: str,
        new_password: str,
    ) -> None:
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )

        if not verify_password(current_password, user.password_hash):
            raise ApiError(
                code="INVALID_PASSWORD",
                message="Current password is incorrect.",
                status_code=400,
            )

        if not new_password or not new_password.strip():
            raise ApiError(
                code="INVALID_PASSWORD",
                message="New password must not be empty.",
                status_code=400,
            )
        try:
            validate_password_policy(new_password)
        except ValueError as exc:
            raise ApiError(
                code="INVALID_PASSWORD",
                message=str(exc),
                status_code=400,
            ) from exc

        if verify_password(new_password, user.password_hash):
            raise ApiError(
                code="INVALID_PASSWORD",
                message="New password must be different from the current password.",
                status_code=400,
            )

        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.now(tz=UTC)
        self.db.commit()

    def get_account_activity(
        self,
        *,
        auth: AuthContext,
        limit: int = 50,
    ) -> list[Any]:
        return AuditService(self.db).repo.list_for_actor(
            tenant_id=auth.tenant_id,
            actor_user_id=auth.user_id,
            limit=max(1, min(limit, 200)),
        )

    def export_account_data(self, *, auth: AuthContext) -> ExportAccountPayload:
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )

        counts = {
            "documents": self._count_statement(
                select(func.count())
                .select_from(Document)
                .where(
                    Document.tenant_id == auth.tenant_id,
                    Document.uploaded_by_user_id == auth.user_id,
                )
            ),
            "queries": self._count_statement(
                select(func.count())
                .select_from(Query)
                .where(
                    Query.tenant_id == auth.tenant_id,
                    Query.user_id == auth.user_id,
                )
            ),
            "conversations": self._count_statement(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.tenant_id == auth.tenant_id,
                    Conversation.user_id == auth.user_id,
                )
            ),
            "comments": self._count_statement(
                select(func.count())
                .select_from(Comment)
                .where(
                    Comment.tenant_id == auth.tenant_id,
                    Comment.user_id == auth.user_id,
                )
            ),
            "pinned_findings": self._count_statement(
                select(func.count())
                .select_from(PinnedFinding)
                .where(
                    PinnedFinding.tenant_id == auth.tenant_id,
                    PinnedFinding.user_id == auth.user_id,
                )
            ),
            "collections_access": self._count_statement(
                select(func.count())
                .select_from(CollectionPermission)
                .where(CollectionPermission.user_id == auth.user_id)
            ),
        }

        return {
            "account": {
                "user_id": str(user.id),
                "tenant_id": str(user.tenant_id),
                "email": user.email,
                "roles": sorted(
                    self.roles.get_role_names_for_user(auth.tenant_id, user.id)
                ),
                "status": "active" if user.is_active else "disabled",
                "totp_enabled": bool(user.totp_enabled),
                "created_at": user.created_at,
                "last_login_at": user.last_login_at,
            },
            "workspace_counts": counts,
            "recent_activity": self.get_account_activity(auth=auth, limit=50),
        }

    def delete_own_account(
        self,
        *,
        auth: AuthContext,
        raw_refresh_token: str | None,
        password: str,
    ) -> None:
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )
        if self._is_bootstrap_super_admin_email(user.email):
            raise ApiError(
                code="FORBIDDEN",
                message="The protected owner account cannot delete itself from the app.",
                status_code=403,
            )
        if not verify_password(password, user.password_hash):
            raise ApiError(
                code="INVALID_PASSWORD",
                message="Password is incorrect. Account was not deleted.",
                status_code=400,
            )

        if raw_refresh_token:
            self.refresh_tokens.revoke_by_raw_token(
                tenant_id=auth.tenant_id,
                raw_refresh_token=raw_refresh_token,
                hash_secret=self.settings.refresh_token_hash_secret,
            )

        self.refresh_tokens.revoke_all_for_user(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            reason="self_deleted",
        )
        storage = StorageService(self.settings)
        objects = list(
            self.db.execute(
                select(Document.storage_bucket, Document.storage_object_key).where(
                    Document.tenant_id == auth.tenant_id,
                    Document.uploaded_by_user_id == auth.user_id,
                )
            ).all()
        )
        for bucket, object_key in objects:
            try:
                storage.delete_object(bucket=str(bucket), object_key=str(object_key))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to delete self-owned object from storage.",
                    extra={
                        "tenant_id": str(auth.tenant_id),
                        "user_id": str(auth.user_id),
                        "bucket": str(bucket),
                        "object_key": str(object_key),
                    },
                    exc_info=True,
                )
        self.db.execute(
            delete(Query).where(
                Query.tenant_id == auth.tenant_id,
                Query.user_id == auth.user_id,
            )
        )
        self.db.execute(
            delete(Document).where(
                Document.tenant_id == auth.tenant_id,
                Document.uploaded_by_user_id == auth.user_id,
            )
        )
        self.users.delete(tenant_id=auth.tenant_id, user=user)
        if self.users.count_by_tenant(auth.tenant_id) == 0:
            tenant = self.tenants.get_by_id(auth.tenant_id)
            if tenant is not None:
                self.tenants.delete(tenant=tenant)
        self.db.commit()

    def save_cookie_preferences(
        self,
        *,
        auth: AuthContext,
        essential: bool,
        analytics: bool,
        marketing: bool,
    ) -> None:
        AuditService(self.db).write_event(
            tenant_id=auth.tenant_id,
            action="auth.cookie_preferences.updated",
            resource_type="privacy",
            actor_user_id=auth.user_id,
            details={
                "essential": str(bool(essential)).lower(),
                "analytics": str(bool(analytics)).lower(),
                "marketing": str(bool(marketing)).lower(),
            },
        )
        self.db.commit()

    def refresh(self, *, raw_refresh_token: str) -> RefreshResult:
        tenant_id = self._extract_tenant_from_refresh_token(raw_refresh_token)
        token_hash = hash_refresh_token(
            raw_refresh_token,
            self.settings.refresh_token_hash_secret,
        )
        token_row = self.refresh_tokens.get_by_hash(tenant_id, token_hash)

        if token_row is None:
            raise ApiError(
                code="INVALID_REFRESH_TOKEN",
                message="Refresh token is invalid.",
                status_code=401,
            )

        now = datetime.now(tz=UTC)

        if token_row.rotated_at is not None:
            self.refresh_tokens.revoke_family(
                tenant_id=tenant_id,
                token_family_id=token_row.token_family_id,
                reason="token_reuse_detected",
            )
            self.db.commit()
            raise ApiError(
                code="REFRESH_TOKEN_REUSED",
                message="Refresh token reuse detected.",
                status_code=401,
            )

        if token_row.revoked_at is not None:
            raise ApiError(
                code="REFRESH_TOKEN_REVOKED",
                message="Refresh token has been revoked.",
                status_code=401,
            )

        if token_row.expires_at <= now:
            self.refresh_tokens.revoke_token(
                tenant_id=tenant_id,
                token=token_row,
                reason="expired",
            )
            self.db.commit()
            raise ApiError(
                code="REFRESH_TOKEN_EXPIRED",
                message="Refresh token is expired.",
                status_code=401,
            )

        user = self.users.get_by_id(tenant_id, token_row.user_id)
        if user is None or not user.is_active:
            self.refresh_tokens.revoke_family(
                tenant_id=tenant_id,
                token_family_id=token_row.token_family_id,
                reason="user_inactive_or_deleted",
            )
            self.db.commit()
            raise ApiError(
                code="AUTH_USER_NOT_ACTIVE",
                message="User account is not active.",
                status_code=401,
            )

        role_names = self._effective_role_names_for_user(user=user)
        if not role_names:
            raise ApiError(
                code="ROLE_ASSIGNMENT_REQUIRED",
                message="User has no assigned roles.",
                status_code=403,
            )

        self.refresh_tokens.mark_rotated(tenant_id=tenant_id, token=token_row)

        new_raw_refresh_token = self._mint_refresh_token(tenant_id=tenant_id)
        new_token_row = RefreshToken(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            user_id=user.id,
            token_hash=hash_refresh_token(
                new_raw_refresh_token,
                self.settings.refresh_token_hash_secret,
            ),
            token_family_id=token_row.token_family_id,
            expires_at=self._refresh_expiry(),
        )
        self.refresh_tokens.create(new_token_row)

        access_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            roles=role_names,
            access_token_version=user.access_token_version,
            settings=self.settings,
        )
        self.db.commit()

        return RefreshResult(
            access_token=access_token,
            refresh_token=new_raw_refresh_token,
            expires_in=self.settings.jwt_access_ttl_minutes * 60,
        )

    def logout(self, *, auth: AuthContext, raw_refresh_token: str | None) -> None:
        self._revoke_access_token(auth=auth, reason="logout")

        if raw_refresh_token is None:
            return

        tenant_id = self._extract_tenant_from_refresh_token(raw_refresh_token)
        if tenant_id != auth.tenant_id:
            raise ApiError(
                code="TENANT_SCOPE_MISMATCH",
                message="Refresh token tenant does not match authenticated tenant.",
                status_code=403,
            )

        token_hash = hash_refresh_token(
            raw_refresh_token,
            self.settings.refresh_token_hash_secret,
        )
        token_row = self.refresh_tokens.get_by_hash(tenant_id, token_hash)
        if token_row is None:
            return

        if token_row.user_id != auth.user_id:
            raise ApiError(
                code="FORBIDDEN",
                message="Cannot revoke another user's refresh token.",
                status_code=403,
            )

        self.refresh_tokens.revoke_token(
            tenant_id=tenant_id,
            token=token_row,
            reason="logout",
        )
        self.db.commit()

    def logout_all(self, *, auth: AuthContext) -> None:
        """Invalidate all current access tokens and revoke all refresh tokens for the user."""
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found.",
                status_code=404,
            )

        invalidated_at = datetime.now(tz=UTC)
        user.access_token_version += 1
        user.updated_at = invalidated_at
        self._revoke_access_token(auth=auth, reason="logout_all")
        self.refresh_tokens.revoke_all_for_user(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            reason="logout_all",
        )
        self.db.commit()

    def _ensure_user_can_authenticate(self, *, user: User) -> None:
        if not user.is_active:
            raise ApiError(
                code="AUTH_USER_NOT_ACTIVE",
                message="User account is not active.",
                status_code=401,
            )
        if user.locked_until is not None and user.locked_until > datetime.now(tz=UTC):
            raise ApiError(
                code="AUTH_USER_LOCKED",
                message="User account is temporarily locked.",
                status_code=423,
            )

    def _effective_role_names_for_user(
        self,
        *,
        user: User,
        tenant_id: uuid.UUID | None = None,
    ) -> frozenset[str]:
        resolved_tenant_id = tenant_id or getattr(user, "tenant_id", None)
        if resolved_tenant_id is None:
            raise ApiError(
                code="ROLE_ASSIGNMENT_REQUIRED",
                message="User tenant scope is unavailable for role resolution.",
                status_code=500,
            )
        role_names = canonicalize_role_names(
            self.roles.get_role_names_for_user(resolved_tenant_id, user.id)
        )
        return role_names

    def _mint_refresh_token(self, *, tenant_id: uuid.UUID) -> str:
        opaque_part = generate_secure_token(64)
        return f"{tenant_id}.{opaque_part}"

    def _extract_tenant_from_refresh_token(self, raw_refresh_token: str) -> uuid.UUID:
        parts = raw_refresh_token.split(".", maxsplit=1)
        if len(parts) != 2:
            raise ApiError(
                code="INVALID_REFRESH_TOKEN",
                message="Refresh token format is invalid.",
                status_code=401,
            )

        tenant_part, opaque = parts
        if len(opaque) < 32:
            raise ApiError(
                code="INVALID_REFRESH_TOKEN",
                message="Refresh token format is invalid.",
                status_code=401,
            )

        try:
            return uuid.UUID(tenant_part)
        except ValueError as exc:
            raise ApiError(
                code="INVALID_REFRESH_TOKEN",
                message="Refresh token format is invalid.",
                status_code=401,
            ) from exc

    def _refresh_expiry(self) -> datetime:
        return datetime.now(tz=UTC) + timedelta(days=self.settings.jwt_refresh_ttl_days)

    # ------------------------------------------------------------------
    # JWT denylist helper
    # ------------------------------------------------------------------

    def _denylist_access_token(self, token_id: str) -> None:
        """Add a JTI to the Redis denylist with TTL matching access token lifetime."""
        try:
            from app.services.system.cache_service import (
                get_redis_client,
            )  # noqa: PLC0415

            rc = get_redis_client()
            ttl = self.settings.jwt_access_ttl_minutes * 60 + 30  # small buffer
            rc.setex(f"jwt:deny:{token_id}", ttl, "1")
        except Exception:  # noqa: BLE001
            logger.warning("Failed to add JTI to denylist", exc_info=True)

    def _revoke_access_token(self, *, auth: AuthContext, reason: str) -> None:
        if not self.revoked_access_tokens.exists(
            tenant_id=auth.tenant_id,
            token_id=auth.token_id,
        ):
            self.revoked_access_tokens.create(
                RevokedAccessToken(
                    id=generate_uuid7_with_fallback(),
                    tenant_id=auth.tenant_id,
                    user_id=auth.user_id,
                    token_id=auth.token_id,
                    reason=reason,
                    expires_at=datetime.now(tz=UTC)
                    + timedelta(
                        minutes=self.settings.jwt_access_ttl_minutes, seconds=30
                    ),
                )
            )
        self._denylist_access_token(auth.token_id)

    def _totp_crypto(self) -> ProviderSecretCrypto:
        effective_settings = self.settings.model_copy(
            update={
                "provider_secret_active_kid": self.settings.effective_totp_secret_active_kid,
                "provider_secret_keyring_json": self.settings.effective_totp_secret_keyring_json,
            }
        )
        return ProviderSecretCrypto(settings=effective_settings)

    @staticmethod
    def _totp_aad(*, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bytes:
        return f"{tenant_id}:{user_id}:totp".encode()

    def _encrypt_totp_secret(self, *, user: User, secret: str) -> str:
        encrypted = self._totp_crypto().encrypt(
            secret,
            aad=self._totp_aad(tenant_id=user.tenant_id, user_id=user.id),
        )
        payload = {
            "v": 1,
            "kid": encrypted.kid,
            "nonce": urlsafe_b64encode(encrypted.nonce).decode("utf-8"),
            "ciphertext": urlsafe_b64encode(encrypted.ciphertext).decode("utf-8"),
        }
        return json.dumps(payload, separators=(",", ":"))

    def _decrypt_totp_secret(self, *, user: User) -> str:
        if not user.totp_secret:
            raise ApiError(
                code="2FA_NOT_SETUP",
                message="Two-factor authentication is not configured for this account.",
                status_code=400,
            )

        try:
            payload = json.loads(user.totp_secret)
        except json.JSONDecodeError:
            return user.totp_secret

        if not isinstance(payload, dict) or payload.get("v") != 1:
            return user.totp_secret

        try:
            nonce = urlsafe_b64decode(str(payload["nonce"]).encode("utf-8"))
            ciphertext = urlsafe_b64decode(str(payload["ciphertext"]).encode("utf-8"))
            plaintext = self._totp_crypto().decrypt(
                nonce=nonce,
                ciphertext=ciphertext,
                kid=str(payload["kid"]),
                aad=self._totp_aad(tenant_id=user.tenant_id, user_id=user.id),
            )
        except (KeyError, ValueError, ProviderSecretCryptoError) as exc:
            raise ApiError(
                code="2FA_SECRET_UNAVAILABLE",
                message="Two-factor authentication secret could not be loaded.",
                status_code=500,
            ) from exc
        return plaintext.decode("utf-8")

    # ------------------------------------------------------------------
    # Pending 2FA token (short-lived JWT for the 2FA challenge step)
    # ------------------------------------------------------------------

    def _mint_pending_2fa_token(
        self, *, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> str:
        import jwt as pyjwt  # noqa: PLC0415

        now = datetime.now(tz=UTC)
        payload = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "type": "2fa_pending",
            "jti": str(generate_uuid7_with_fallback()),
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
        }
        return pyjwt.encode(payload, self.settings.jwt_secret, algorithm="HS256")

    def _decode_pending_2fa_token(self, token: str) -> dict[str, Any]:
        import jwt as pyjwt  # noqa: PLC0415

        try:
            claims = pyjwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=["HS256"],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
            )
        except pyjwt.ExpiredSignatureError as exc:
            raise ApiError(
                code="2FA_TOKEN_EXPIRED",
                message="Two-factor authentication token has expired. Please log in again.",
                status_code=401,
            ) from exc
        except pyjwt.InvalidTokenError as exc:
            raise ApiError(
                code="INVALID_2FA_TOKEN",
                message="Invalid two-factor authentication token.",
                status_code=401,
            ) from exc

        if claims.get("type") != "2fa_pending":
            raise ApiError(
                code="INVALID_2FA_TOKEN",
                message="Invalid two-factor authentication token.",
                status_code=401,
            )
        return claims

    # ------------------------------------------------------------------
    # 2FA: verify TOTP during login
    # ------------------------------------------------------------------

    def verify_totp_login(self, *, pending_token: str, code: str) -> LoginResult:
        """Complete login after 2FA challenge."""
        claims = self._decode_pending_2fa_token(pending_token)
        user_id = uuid.UUID(claims["sub"])
        tenant_id = uuid.UUID(claims["tenant_id"])

        user = self.users.get_by_id(tenant_id, user_id)
        if user is None or not user.is_active:
            raise ApiError(
                code="USER_NOT_FOUND",
                message="User not found or inactive.",
                status_code=401,
            )

        if not user.totp_enabled or not user.totp_secret:
            raise ApiError(
                code="2FA_NOT_ENABLED",
                message="Two-factor authentication is not enabled for this account.",
                status_code=400,
            )

        totp = pyotp.TOTP(self._decrypt_totp_secret(user=user))
        if not totp.verify(code, valid_window=1):
            # Try backup codes
            if not self._use_backup_code(user, code):
                raise ApiError(
                    code="INVALID_TOTP_CODE",
                    message="Invalid two-factor authentication code.",
                    status_code=401,
                )

        role_names = self.roles.get_role_names_for_user(tenant_id, user.id)
        if not role_names:
            raise ApiError(
                code="ROLE_ASSIGNMENT_REQUIRED",
                message="User has no assigned roles.",
                status_code=403,
            )

        access_token = create_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            roles=role_names,
            access_token_version=user.access_token_version,
            settings=self.settings,
        )

        raw_refresh_token = self._mint_refresh_token(tenant_id=tenant_id)
        hashed_refresh_token = hash_refresh_token(
            raw_refresh_token,
            self.settings.refresh_token_hash_secret,
        )
        refresh_token_row = RefreshToken(
            id=generate_uuid7_with_fallback(),
            tenant_id=tenant_id,
            user_id=user.id,
            token_hash=hashed_refresh_token,
            token_family_id=generate_uuid7_with_fallback(),
            expires_at=self._refresh_expiry(),
        )
        self.refresh_tokens.create(refresh_token_row)
        self.db.commit()

        return LoginResult(
            user=user,
            roles=sorted(role_names),
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=self.settings.jwt_access_ttl_minutes * 60,
        )

    # ------------------------------------------------------------------
    # 2FA: setup / confirm / disable
    # ------------------------------------------------------------------

    def setup_totp(self, *, auth: AuthContext) -> TotpSetupResult:
        """Generate a new TOTP secret (does NOT enable 2FA yet)."""
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND", message="User not found.", status_code=404
            )

        if user.totp_enabled:
            raise ApiError(
                code="2FA_ALREADY_ENABLED",
                message="Two-factor authentication is already enabled. Disable it first.",
                status_code=409,
            )

        secret = pyotp.random_base32()
        user.totp_secret = self._encrypt_totp_secret(user=user, secret=secret)
        user.totp_enabled = False
        user.updated_at = datetime.now(tz=UTC)
        self.db.commit()

        provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="AverQel",
        )

        return TotpSetupResult(secret=secret, provisioning_uri=provisioning_uri)

    def confirm_totp(self, *, auth: AuthContext, code: str) -> list[str]:
        """Verify the TOTP code works and activate 2FA. Returns backup codes."""
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND", message="User not found.", status_code=404
            )

        if user.totp_enabled:
            raise ApiError(
                code="2FA_ALREADY_ENABLED",
                message="Two-factor authentication is already active.",
                status_code=409,
            )

        if not user.totp_secret:
            raise ApiError(
                code="2FA_NOT_SETUP",
                message="Call /auth/2fa/setup first to generate a TOTP secret.",
                status_code=400,
            )

        totp = pyotp.TOTP(self._decrypt_totp_secret(user=user))
        if not totp.verify(code, valid_window=1):
            raise ApiError(
                code="INVALID_TOTP_CODE",
                message="Invalid TOTP code. Ensure your authenticator app clock is synced.",
                status_code=400,
            )

        # Generate backup codes
        raw_codes = [
            secrets.token_hex(_TOTP_BACKUP_CODE_LENGTH // 2)
            for _ in range(_TOTP_BACKUP_CODE_COUNT)
        ]
        hashed_codes = [hashlib.sha256(c.encode()).hexdigest() for c in raw_codes]
        user.totp_backup_codes = json.dumps(hashed_codes)
        user.totp_enabled = True
        user.updated_at = datetime.now(tz=UTC)
        self.db.commit()

        return raw_codes

    def disable_totp(self, *, auth: AuthContext, password: str) -> None:
        """Disable 2FA after verifying the user's password."""
        user = self.users.get_by_id(auth.tenant_id, auth.user_id)
        if user is None:
            raise ApiError(
                code="USER_NOT_FOUND", message="User not found.", status_code=404
            )

        if not user.totp_enabled:
            raise ApiError(
                code="2FA_NOT_ENABLED",
                message="Two-factor authentication is not currently enabled.",
                status_code=400,
            )

        if not verify_password(password, user.password_hash):
            raise ApiError(
                code="INVALID_PASSWORD",
                message="Password is incorrect.",
                status_code=400,
            )

        user.totp_secret = None
        user.totp_enabled = False
        user.totp_backup_codes = None
        user.updated_at = datetime.now(tz=UTC)
        self.db.commit()

    # ------------------------------------------------------------------
    # Backup code helper
    # ------------------------------------------------------------------

    def _use_backup_code(self, user: User, code: str) -> bool:
        """Try to match and consume a backup code. Returns True on success."""
        if not user.totp_backup_codes:
            return False

        try:
            hashed_codes: list[str] = json.loads(user.totp_backup_codes)
        except (json.JSONDecodeError, TypeError):
            return False

        code_hash = hashlib.sha256(code.strip().encode()).hexdigest()
        if code_hash not in hashed_codes:
            return False

        hashed_codes.remove(code_hash)
        user.totp_backup_codes = json.dumps(hashed_codes) if hashed_codes else None
        user.updated_at = datetime.now(tz=UTC)
        return True

    def _count_statement(self, statement: Any) -> int:
        return int(self.db.execute(statement).scalar_one() or 0)
