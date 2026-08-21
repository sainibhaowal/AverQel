from __future__ import annotations

from http.cookies import SimpleCookie

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
