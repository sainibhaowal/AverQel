from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from mcp.shared.auth import (
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from sqlalchemy import select

import app.services.integrations.connector_oauth_service as connector_oauth_service
from app.core.auth import create_access_token
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.models.integrations.connector import Connector, ConnectorStatus
from app.models.integrations.connector_secret import ConnectorSecret
from app.models.integrations.integration import Integration
from app.services.integrations.connector_oauth_service import ConnectorOAuthService
from app.services.security.connector_secret_crypto import ConnectorSecretCrypto


def _configure_secret_backend(settings: Settings) -> None:
    key = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode("utf-8")
    settings.provider_secret_backend = "env_keyring"
    settings.provider_secret_active_kid = "kid-active"
    settings.provider_secret_keyring_json = json.dumps({"kid-active": key})
    settings.averqel_public_origin = "https://averqel.localhost"
    settings.connector_oauth_redirect_uri = (
        "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
    )
    settings.connector_oauth_frontend_redirect_uri = (
        "https://averqel.localhost/dashboard/connectors"
    )
    settings.connector_google_oauth_client_id = "google-client-id"
    settings.connector_google_oauth_client_secret = "google-client-secret"
    settings.connector_github_oauth_client_id = "github-client-id"
    settings.connector_github_oauth_client_secret = "github-client-secret"
    settings.connector_slack_oauth_client_id = "slack-client-id"
    settings.connector_slack_oauth_client_secret = "slack-client-secret"
    settings.connector_notion_oauth_client_id = "notion-client-id"
    settings.connector_notion_oauth_client_secret = "notion-client-secret"


def _auth_headers(seeded) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"admin"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def _seed_connector(db_session, tenant_id, user_id, slug: str) -> Connector:
    integration = (
        db_session.execute(select(Integration).where(Integration.slug == slug))
        .scalars()
        .first()
    )
    if integration is None:
        integration = Integration(
            id=uuid4(),
            name=f"{slug} integration {uuid4().hex[:8]}",
            slug=slug,
            description=f"MCP test integration for {slug}",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        integration_id=integration.id,
        name=f"{slug} connector {uuid4().hex[:8]}",
        config={},
        sync_frequency="daily",
    )
    db_session.add(connector)
    db_session.commit()
    return connector


def _mcp_metadata() -> tuple[ProtectedResourceMetadata, OAuthMetadata]:
    resource_metadata = ProtectedResourceMetadata(
        resource="https://drivemcp.googleapis.com/mcp/v1",
        authorization_servers=["https://auth.example.com"],
        scopes_supported=["https://www.googleapis.com/auth/drive"],
        resource_name="Google Drive MCP",
    )
    oauth_metadata = OAuthMetadata(
        issuer="https://auth.example.com",
        authorization_endpoint="https://auth.example.com/authorize",
        token_endpoint="https://auth.example.com/token",
        registration_endpoint="https://auth.example.com/register",
        scopes_supported=["https://www.googleapis.com/auth/drive"],
        response_types_supported=["code"],
        grant_types_supported=["authorization_code", "refresh_token"],
        token_endpoint_auth_methods_supported=["none"],
        code_challenge_methods_supported=["S256"],
    )
    return resource_metadata, oauth_metadata


def test_connector_oauth_start_builds_mcp_authorization_url(
    db_session,
    seed_user,
    settings,
    monkeypatch,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant", "mcp@example.com", "Password!123", ("admin",))
    connector = _seed_connector(
        db_session, seeded.tenant_id, seeded.user_id, "google-drive"
    )

    resource_metadata, oauth_metadata = _mcp_metadata()
    service = ConnectorOAuthService(db_session, settings)

    monkeypatch.setattr(
        ConnectorOAuthService,
        "_discover_mcp_metadata",
        lambda self, server_url: (resource_metadata, oauth_metadata),
    )
    available, authorization_url, message = service.start(
        tenant_id=seeded.tenant_id,
        actor_user_id=seeded.user_id,
        connector_id=connector.id,
    )

    assert available is True
    assert authorization_url is not None
    assert "OAuth flow initialized" in message
    parsed = urlparse(authorization_url)
    params = parse_qs(parsed.query)
    assert params["client_id"] == [settings.connector_google_oauth_client_id]
    assert params["redirect_uri"] == [settings.connector_oauth_redirect_uri]
    assert "https://www.googleapis.com/auth/drive" in params["scope"][0]
    assert params["response_type"] == ["code"]
    assert params["resource"] == [str(resource_metadata.resource)]
    assert "state" in params


def test_connector_oauth_start_returns_clean_error_when_not_configured(
    db_session,
    seed_user,
    settings,
    monkeypatch,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant", "mcp@example.com", "Password!123", ("admin",))
    connector = _seed_connector(
        db_session, seeded.tenant_id, seeded.user_id, "google-drive"
    )

    service = ConnectorOAuthService(db_session, settings)

    settings.connector_google_oauth_client_secret = None

    with pytest.raises(ApiError) as exc_info:
        service.start(
            tenant_id=seeded.tenant_id,
            actor_user_id=seeded.user_id,
            connector_id=connector.id,
        )

    assert exc_info.value.code == "CONNECTOR_OAUTH_INVALID"
    assert "OAuth is not configured on this deployment" in str(exc_info.value.message)


def test_connector_oauth_start_returns_clean_error_on_network_failure(
    db_session,
    seed_user,
    settings,
    monkeypatch,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant", "mcp@example.com", "Password!123", ("admin",))
    connector = _seed_connector(
        db_session, seeded.tenant_id, seeded.user_id, "google-drive"
    )

    service = ConnectorOAuthService(db_session, settings)

    observed_server_urls: list[str] = []

    def _capture_and_fail(self, server_url):  # type: ignore[no-untyped-def]
        observed_server_urls.append(server_url)
        raise httpx.RequestError(
            "network unreachable",
            request=httpx.Request("GET", "https://example.invalid"),
        )

    monkeypatch.setattr(
        ConnectorOAuthService, "_discover_mcp_metadata", _capture_and_fail
    )

    with pytest.raises(ApiError) as exc_info:
        service.start(
            tenant_id=seeded.tenant_id,
            actor_user_id=seeded.user_id,
            connector_id=connector.id,
        )

    assert exc_info.value.code == "CONNECTOR_OAUTH_INVALID"
    assert "Unable to reach MCP connector service" in str(exc_info.value.message)
    assert observed_server_urls == ["https://drivemcp.googleapis.com/mcp/v1"]


def test_connector_oauth_readiness_reports_configured_for_mcp_integration(
    db_session,
    seed_user,
    settings,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant", "mcp@example.com", "Password!123", ("admin",))
    connector = _seed_connector(
        db_session, seeded.tenant_id, seeded.user_id, "google-drive"
    )

    service = ConnectorOAuthService(db_session, settings)
    integration = db_session.get(Integration, connector.integration_id)
    assert integration is not None

    readiness = service.readiness(integration=integration)

    assert readiness["configured"] is True
    assert readiness["missing"] == []
    assert "OAuth client ready" in readiness["message"]


def test_connector_oauth_start_requires_mcp_sdk(
    db_session,
    seed_user,
    settings,
    monkeypatch,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant", "mcp@example.com", "Password!123", ("admin",))
    connector = _seed_connector(
        db_session, seeded.tenant_id, seeded.user_id, "google-drive"
    )

    service = ConnectorOAuthService(db_session, settings)
    monkeypatch.setattr(connector_oauth_service, "MCP_SDK_AVAILABLE", False)

    with pytest.raises(ApiError) as exc_info:
        service.start(
            tenant_id=seeded.tenant_id,
            actor_user_id=seeded.user_id,
            connector_id=connector.id,
        )

    assert exc_info.value.code == "CONNECTOR_OAUTH_INVALID"
    assert "MCP support is not installed" in str(exc_info.value.message)


def test_list_integrations_exposes_mcp_readiness(
    client,
    seed_user,
    settings,
    db_session,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant", "mcp@example.com", "Password!123", ("admin",))
    _seed_connector(db_session, seeded.tenant_id, seeded.user_id, "google-drive")
    headers = _auth_headers(seeded)

    response = client.get("/api/v1/integrations", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    google_drive = next(item for item in payload if item["slug"] == "google-drive")
    assert google_drive["oauth_status"]["configured"] is True
    assert google_drive["oauth_status"]["missing"] == []
    assert "OAuth client ready" in google_drive["oauth_status"]["message"]


@pytest.mark.asyncio
async def test_connector_oauth_callback_persists_mcp_credentials(
    db_session,
    seed_user,
    settings,
    monkeypatch,
):
    _configure_secret_backend(settings)
    seeded = seed_user("MCP Tenant 2", "mcp2@example.com", "Password!123", ("admin",))
    connector = _seed_connector(
        db_session, seeded.tenant_id, seeded.user_id, "google-drive"
    )

    resource_metadata, oauth_metadata = _mcp_metadata()
    service = ConnectorOAuthService(db_session, settings)

    monkeypatch.setattr(
        ConnectorOAuthService,
        "_discover_mcp_metadata",
        lambda self, server_url: (resource_metadata, oauth_metadata),
    )
    monkeypatch.setattr(
        ConnectorOAuthService,
        "_exchange_token",
        lambda self, **kwargs: OAuthToken(
            access_token="mcp-access-token",
            refresh_token="mcp-refresh-token",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/drive",
        ),
    )

    _available, authorization_url, _message = service.start(
        tenant_id=seeded.tenant_id,
        actor_user_id=seeded.user_id,
        connector_id=connector.id,
    )
    state = parse_qs(urlparse(authorization_url or "").query)["state"][0]

    returned_connector = await service.callback(code="mcp-code-123", state=state)

    assert returned_connector.status == ConnectorStatus.ACTIVE

    secret = (
        db_session.execute(
            select(ConnectorSecret).where(
                ConnectorSecret.connector_id == connector.id,
                ConnectorSecret.secret_type == "credentials",
            )
        )
        .scalars()
        .first()
    )
    assert secret is not None

    crypto = ConnectorSecretCrypto(settings)
    decrypted = crypto.decrypt(
        ciphertext=secret.secret_ciphertext,
        nonce=secret.secret_nonce,
        kid=secret.secret_kid,
        aad=str(seeded.tenant_id).encode(),
    )
    payload = json.loads(decrypted.decode("utf-8"))
    assert payload["auth_mode"] == "mcp"
    assert payload["server_url"] == "https://drivemcp.googleapis.com/mcp/v1"
    assert payload["token"] == "mcp-access-token"
    assert payload["refresh_token"] == "mcp-refresh-token"
    assert payload["client_id"] == "google-client-id"
    assert payload["mcp_tools"]
