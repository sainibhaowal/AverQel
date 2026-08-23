from __future__ import annotations

from http.cookies import SimpleCookie
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import Response

from app.auth.services import oauth_login_service
from app.auth.services.oauth_login_service import OAuthLoginService
from app.core.config import get_settings
from app.core.errors import ApiError


def _settings():
    return get_settings().model_copy(
        update={
            "auth_google_oauth_client_id": "google-client",
            "auth_google_oauth_client_secret": "google-secret",
            "auth_oauth_redirect_uri": "https://app.example.com/api/v1/auth/oauth/{provider}/callback",
            "auth_oauth_frontend_redirect_uri": "https://app.example.com/auth/login",
        }
    )


def test_start_uses_signed_state_and_pkce() -> None:
    response = Response()
    service = OAuthLoginService(None, _settings())

    url = service.start(provider_name="google", response=response)

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge_method=S256" in url
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    state = cookie["averqel_auth_oauth_state"].value
    payload = service._verify_state(state, "google")
    assert payload["provider"] == "google"
    assert isinstance(payload["verifier"], str)


def test_state_tampering_is_rejected() -> None:
    service = OAuthLoginService(None, _settings())
    response = Response()
    service.start(provider_name="google", response=response)
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])

    with pytest.raises(ApiError) as error:
        service._verify_state(cookie["averqel_auth_oauth_state"].value + "x", "google")

    assert error.value.code == "OAUTH_STATE_INVALID"


def test_google_identity_requires_verified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OAuthLoginService(None, _settings())
    provider = service.provider("google")

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "sub": "google-user",
                "email": "person@example.com",
                "email_verified": False,
            }

    monkeypatch.setattr(oauth_login_service.httpx, "get", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(ApiError) as error:
        service._fetch_identity(provider, "provider-access-token")

    assert error.value.code == "OAUTH_EMAIL_UNVERIFIED"


def test_new_user_callback_restores_bypass_context_before_identity_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An OAuth identity insert follows a commit when OAuth creates a user."""

    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    user = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        tenant_id=tenant_id,
    )
    contexts: list[str] = []

    class FakeSession:
        def execute(self, *_args, **_kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        def add(self, _identity) -> None:
            pass

        def flush(self) -> None:
            pass

    class FakeUsers:
        @staticmethod
        def get_by_email_global(_email: str):
            return None

    class FakeAuthService:
        def __init__(self, _db, _settings) -> None:
            self.users = FakeUsers()

        @staticmethod
        def register(**_kwargs):
            return user

        @staticmethod
        def complete_external_login(**_kwargs):
            return "logged-in"

    service = OAuthLoginService(FakeSession(), _settings())
    monkeypatch.setattr(oauth_login_service, "AuthService", FakeAuthService)
    monkeypatch.setattr(
        oauth_login_service,
        "set_db_tenant_context",
        lambda _db, tenant: contexts.append(str(tenant)),
    )
    monkeypatch.setattr(
        service,
        "_verify_state",
        lambda _cookie, _provider: {"state": "expected", "verifier": "verifier"},
    )
    monkeypatch.setattr(service, "_exchange_code", lambda *_args: "provider-token")
    monkeypatch.setattr(
        service,
        "_fetch_identity",
        lambda *_args: ("google-subject", "person@example.com", None),
    )

    result = service.authenticate_callback(
        provider_name="google",
        code="code",
        state="expected",
        state_cookie="cookie",
    )

    assert result == "logged-in"
    assert contexts == ["bypass", "bypass"]
