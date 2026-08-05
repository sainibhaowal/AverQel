from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.auth.dependencies import AuthContext
from app.auth.services.auth_service import AuthService
from app.core.config import get_settings
from app.core.errors import ApiError

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class _DB:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        return None


class _Users:
    def __init__(self, user=None) -> None:  # type: ignore[no-untyped-def]
        self._user = user
        self.failed_called = False
        self.success_called = False

    def get_by_email(self, tenant_id, email):  # type: ignore[no-untyped-def]
        _ = (tenant_id, email)
        return self._user

    def register_failed_login(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.failed_called = True

    def register_successful_login(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.success_called = True

    def get_by_id(self, tenant_id, user_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, user_id)
        return self._user


class _Roles:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def get_role_names_for_user(self, tenant_id, user_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, user_id)
        return self.names


class _RefreshTokens:
    def __init__(self, token=None) -> None:  # type: ignore[no-untyped-def]
        self.token = token
        self.revoked = False
        self.family_revoked = False
        self.rotated = False
        self.created = False

    def get_by_hash(self, tenant_id, token_hash):  # type: ignore[no-untyped-def]
        _ = (tenant_id, token_hash)
        return self.token

    def create(self, row):  # type: ignore[no-untyped-def]
        _ = row
        self.created = True

    def revoke_family(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.family_revoked = True

    def revoke_token(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.revoked = True

    def mark_rotated(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.rotated = True


class _RevokedAccessTokens:
    def __init__(self) -> None:
        self.created = False
        self._exists = False

    def exists(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return self._exists

    def create(self, row):  # type: ignore[no-untyped-def]
        _ = row
        self.created = True
        self._exists = True


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


def _service(settings):  # type: ignore[no-untyped-def]
    svc = AuthService(_DB(), settings)
    svc.users = _Users()
    svc.roles = _Roles(["admin"])
    svc.refresh_tokens = _RefreshTokens()
    svc.revoked_access_tokens = _RevokedAccessTokens()
    return svc


def _user(active: bool = True, locked: bool = False):
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        password_hash="hash",
        is_active=active,
        locked_until=(datetime.now(tz=UTC) + timedelta(minutes=5)) if locked else None,
    )


def _token_row(user_id: UUID, tenant_id: UUID):
    return SimpleNamespace(
        user_id=user_id,
        token_family_id=uuid4(),
        rotated_at=None,
        revoked_at=None,
        expires_at=datetime.now(tz=UTC) + timedelta(days=1),
        tenant_id=tenant_id,
    )


def test_login_unknown_user_raises_invalid_credentials(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = _service(settings)
    svc.users = _Users(None)
    with pytest.raises(ApiError, match="Invalid email or password"):
        svc.login(tenant_id=uuid4(), email="x@example.com", password="pw")


def test_login_bad_password_records_failure(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _service(settings)
    user = _user()
    users = _Users(user)
    svc.users = users
    monkeypatch.setattr("app.auth.services.auth_service.verify_password", lambda p, h: False)

    with pytest.raises(ApiError) as exc:
        svc.login(tenant_id=uuid4(), email="x@example.com", password="bad")
    assert exc.value.code == "INVALID_CREDENTIALS"
    assert users.failed_called is True
    assert svc.db.commits == 1


def test_login_without_roles_raises(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _service(settings)
    svc.users = _Users(_user())
    svc.roles = _Roles([])
    monkeypatch.setattr("app.auth.services.auth_service.verify_password", lambda p, h: True)
    with pytest.raises(ApiError) as exc:
        svc.login(tenant_id=uuid4(), email="x@example.com", password="pw")
    assert exc.value.code == "ROLE_ASSIGNMENT_REQUIRED"


def test_refresh_invalid_hash_not_found(settings) -> None:
    svc = _service(settings)
    with pytest.raises(ApiError) as exc:
        svc.refresh(raw_refresh_token=f"{uuid4()}.{'a' * 32}")
    assert exc.value.code == "INVALID_REFRESH_TOKEN"


def test_refresh_expired_revokes_token(settings) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    svc = _service(settings)
    token = _token_row(user_id=user_id, tenant_id=tenant_id)
    token.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    refresh = _RefreshTokens(token)
    svc.refresh_tokens = refresh
    with pytest.raises(ApiError) as exc:
        svc.refresh(raw_refresh_token=f"{tenant_id}.{'a' * 40}")
    assert exc.value.code == "REFRESH_TOKEN_EXPIRED"
    assert refresh.revoked is True


def test_refresh_inactive_user_revokes_family(settings) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    svc = _service(settings)
    svc.refresh_tokens = _RefreshTokens(_token_row(user_id=user_id, tenant_id=tenant_id))
    svc.users = _Users(_user(active=False))

    with pytest.raises(ApiError) as exc:
        svc.refresh(raw_refresh_token=f"{tenant_id}.{'a' * 40}")
    assert exc.value.code == "AUTH_USER_NOT_ACTIVE"
    assert svc.refresh_tokens.family_revoked is True


def test_refresh_user_without_roles_raises(settings) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    svc = _service(settings)
    svc.refresh_tokens = _RefreshTokens(_token_row(user_id=user_id, tenant_id=tenant_id))
    svc.users = _Users(_user(active=True))
    svc.roles = _Roles([])

    with pytest.raises(ApiError) as exc:
        svc.refresh(raw_refresh_token=f"{tenant_id}.{'a' * 40}")
    assert exc.value.code == "ROLE_ASSIGNMENT_REQUIRED"


def test_logout_none_token_is_noop(settings) -> None:
    svc = _service(settings)
    svc.logout(
        auth=AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=frozenset({"admin"}),
            token_id=str(uuid4()),
        ),
        raw_refresh_token=None,
    )


def test_logout_tenant_mismatch(settings) -> None:
    svc = _service(settings)
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"admin"}),
        token_id=str(uuid4()),
    )
    with pytest.raises(ApiError) as exc:
        svc.logout(auth=auth, raw_refresh_token=f"{uuid4()}.{'a' * 40}")
    assert exc.value.code == "TENANT_SCOPE_MISMATCH"


def test_logout_token_not_found_is_noop(settings) -> None:
    tenant_id = uuid4()
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        roles=frozenset({"admin"}),
        token_id=str(uuid4()),
    )
    svc = _service(settings)
    svc.refresh_tokens = _RefreshTokens(None)
    svc.logout(auth=auth, raw_refresh_token=f"{tenant_id}.{'a' * 40}")


def test_logout_forbidden_user_mismatch(settings) -> None:
    tenant_id = uuid4()
    auth = AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        roles=frozenset({"admin"}),
        token_id=str(uuid4()),
    )
    svc = _service(settings)
    token = _token_row(user_id=uuid4(), tenant_id=tenant_id)
    svc.refresh_tokens = _RefreshTokens(token)
    with pytest.raises(ApiError) as exc:
        svc.logout(auth=auth, raw_refresh_token=f"{tenant_id}.{'a' * 40}")
    assert exc.value.code == "FORBIDDEN"


def test_ensure_user_can_authenticate_paths(settings) -> None:
    svc = _service(settings)
    with pytest.raises(ApiError) as inactive_exc:
        svc._ensure_user_can_authenticate(user=_user(active=False))
    assert inactive_exc.value.code == "AUTH_USER_NOT_ACTIVE"

    with pytest.raises(ApiError) as locked_exc:
        svc._ensure_user_can_authenticate(user=_user(active=True, locked=True))
    assert locked_exc.value.code == "AUTH_USER_LOCKED"


def test_extract_refresh_token_format_errors(settings) -> None:
    svc = _service(settings)

    with pytest.raises(ApiError):
        svc._extract_tenant_from_refresh_token("invalid")

    with pytest.raises(ApiError):
        svc._extract_tenant_from_refresh_token(f"{uuid4()}.short")

    with pytest.raises(ApiError):
        svc._extract_tenant_from_refresh_token(f"not-a-uuid.{'a' * 40}")
