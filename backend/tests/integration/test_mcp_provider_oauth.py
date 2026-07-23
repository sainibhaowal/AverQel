from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.models.mcp_server import MCPEvent, MCPOAuthToken, MCPServer
from app.integrations.services import mcp_oauth_service
from app.integrations.services.connector_secret_crypto import ConnectorSecretCrypto
from app.integrations.services.mcp_oauth_service import MCPServerOAuthService
from app.platform.database.session import set_db_tenant_context
from tests.conftest import SeededUser


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | list[dict[str, object]]):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, _url, **_kwargs):
        return _FakeResponse(
            200,
            {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose",
            },
        )

    def get(self, url, **_kwargs):
        if url.endswith("userinfo"):
            return _FakeResponse(200, {"sub": "google-subject", "email": "owner@example.com", "name": "Owner"})
        raise AssertionError(f"Unexpected identity URL: {url}")


def test_static_provider_oauth_encrypts_pending_data_and_captures_identity(
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-mcp-provider-oauth",
        "mcp-provider-oauth@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    set_db_tenant_context(db_session, seeded.tenant_id)
    settings = get_settings()
    settings.mcp_google_oauth_client_id = "mcp-google-client-id"
    settings.mcp_google_oauth_client_secret = "mcp-google-client-secret"
    settings.mcp_oauth_redirect_uri = "https://averqel.example/api/v1/mcp/oauth/callback"
    server = MCPServer(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        provider_slug="google-gmail",
        name="Google Gmail",
        transport="streamable_http",
        config={
            "server_url": "https://gmailmcp.googleapis.com/mcp/v1",
            "oauth_mode": "mcp_oauth",
            "auth_type": "oauth",
        },
        status="needs_auth",
    )
    db_session.add(server)
    db_session.commit()
    db_session.refresh(server)

    service = MCPServerOAuthService(db_session, settings)
    authorization_url = service.start(server=server, user_id=seeded.user_id)
    params = parse_qs(urlparse(authorization_url).query)
    assert urlparse(authorization_url).netloc == "accounts.google.com"
    assert params["client_id"] == ["mcp-google-client-id"]
    assert params["redirect_uri"] == [settings.mcp_oauth_redirect_uri]
    assert "mcp-google-client-secret" not in authorization_url
    assert "code_challenge" in params

    db_session.refresh(server)
    transaction = db_session.execute(
        select(mcp_oauth_service.MCPOAuthTransaction).where(
            mcp_oauth_service.MCPOAuthTransaction.server_id == server.id
        )
    ).scalar_one()
    assert b"code_verifier" not in transaction.secret_ciphertext
    assert "code_verifier" not in json.dumps(server.config)

    monkeypatch.setattr(mcp_oauth_service, "build_safe_sync_client", lambda **_kwargs: _FakeClient())
    state = params["state"][0]
    service.finish(server=server, code="authorization-code", state=state)

    db_session.refresh(server)
    assert server.account_identity == {
        "provider_subject": "google-subject",
        "account_id": "google-subject",
        "email": "owner@example.com",
        "display_name": "Owner",
    }
    assert "mcp-google-client-secret" not in json.dumps(server.config)
    assert "access-secret" not in json.dumps(server.config)
    assert server.config["oauth_profile"] == "google"
    token = db_session.execute(
        select(MCPOAuthToken).where(MCPOAuthToken.server_id == server.id)
    ).scalar_one()
    plaintext = ConnectorSecretCrypto(settings).decrypt(
        ciphertext=token.secret_ciphertext,
        nonce=token.secret_nonce,
        kid=token.secret_kid,
        aad=str(server.tenant_id).encode(),
    )
    assert json.loads(plaintext)["access_token"] == "access-secret"
    completed = db_session.execute(
        select(MCPEvent).where(MCPEvent.server_id == server.id, MCPEvent.event_type == "oauth_completed")
    ).scalar_one()
    assert completed.payload == {"provider": "google"}


def test_static_provider_disconnect_revokes_and_removes_local_token(
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "tenant-mcp-provider-disconnect",
        "mcp-provider-disconnect@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    set_db_tenant_context(db_session, seeded.tenant_id)
    settings = get_settings()
    settings.mcp_google_oauth_client_id = "mcp-google-client-id"
    settings.mcp_google_oauth_client_secret = "mcp-google-client-secret"
    server = MCPServer(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        provider_slug="google-gmail",
        name="Google Gmail",
        transport="streamable_http",
        config={"server_url": "https://gmailmcp.googleapis.com/mcp/v1", "auth_mode": "mcp"},
        account_identity={"email": "owner@example.com"},
        status="connected",
    )
    db_session.add(server)
    db_session.flush()
    encrypted = ConnectorSecretCrypto(settings).encrypt(
        json.dumps({"access_token": "access-secret", "refresh_token": "refresh-secret"}),
        aad=str(server.tenant_id).encode(),
    )
    db_session.add(
        MCPOAuthToken(
            tenant_id=server.tenant_id,
            user_id=server.user_id,
            server_id=server.id,
            secret_ciphertext=encrypted.ciphertext,
            secret_nonce=encrypted.nonce,
            secret_kid=encrypted.kid,
        )
    )
    db_session.commit()

    class _RevokeClient(_FakeClient):
        def post(self, url, **kwargs):
            assert url.endswith("/revoke")
            assert kwargs["data"]["token"] == "refresh-secret"
            return _FakeResponse(200, {})

    monkeypatch.setattr(mcp_oauth_service, "build_safe_sync_client", lambda **_kwargs: _RevokeClient())
    MCPServerOAuthService(db_session, settings).disconnect(server=server, user_id=seeded.user_id)

    assert db_session.execute(select(MCPOAuthToken).where(MCPOAuthToken.server_id == server.id)).scalar_one_or_none() is None
    db_session.refresh(server)
    assert server.account_identity == {}
    assert server.status == "needs_auth"
