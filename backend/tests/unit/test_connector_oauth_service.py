from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

import app.integrations.services.connector_oauth_service as connector_oauth_service
from app.integrations.models.integration import Integration
from app.integrations.services.connector_oauth_service import ConnectorOAuthService


def _seed_integration(db_session, slug: str) -> Integration:
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
        db_session.commit()
    return integration


def test_connector_oauth_readiness_requires_callback_url(
    db_session,
    settings,
    monkeypatch,
) -> None:
    settings.averqel_public_origin = None
    settings.connector_oauth_redirect_uri = None
    settings.connector_oauth_frontend_redirect_uri = (
        "https://averqel.localhost/dashboard"
    )
    settings.connector_google_oauth_client_id = "google-id"
    settings.connector_google_oauth_client_secret = "google-secret"
    monkeypatch.setattr(connector_oauth_service, "MCP_SDK_AVAILABLE", True)

    service = ConnectorOAuthService(db_session, settings)
    integration = _seed_integration(db_session, "google-drive")

    readiness = service.readiness(integration=integration)

    assert readiness["configured"] is False
    assert readiness["missing"] == ["connector_oauth_redirect_uri"]
    assert "callback URL" in readiness["message"]


def test_connector_oauth_readiness_requires_frontend_redirect_url(
    db_session,
    settings,
    monkeypatch,
) -> None:
    settings.averqel_public_origin = None
    settings.connector_oauth_redirect_uri = (
        "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
    )
    settings.connector_oauth_frontend_redirect_uri = None
    settings.connector_google_oauth_client_id = "google-id"
    settings.connector_google_oauth_client_secret = "google-secret"
    monkeypatch.setattr(connector_oauth_service, "MCP_SDK_AVAILABLE", True)

    service = ConnectorOAuthService(db_session, settings)
    integration = _seed_integration(db_session, "google-drive")

    readiness = service.readiness(integration=integration)

    assert readiness["configured"] is False
    assert readiness["missing"] == ["connector_oauth_frontend_redirect_uri"]
    assert "frontend redirect URL" in readiness["message"]


def test_connector_oauth_derives_redirect_uri_from_public_origin(
    db_session,
    settings,
    monkeypatch,
) -> None:
    settings.averqel_public_origin = "https://averqel.localhost"
    settings.connector_oauth_redirect_uri = None
    settings.connector_oauth_frontend_redirect_uri = (
        "https://averqel.localhost/dashboard"
    )
    monkeypatch.setattr(connector_oauth_service, "MCP_SDK_AVAILABLE", True)

    service = ConnectorOAuthService(db_session, settings)
    
    # Configure provider client secret to make it configured
    settings.connector_google_oauth_client_id = "google-client-id"
    settings.connector_google_oauth_client_secret = "google-client-secret"
    integration = _seed_integration(db_session, "google-drive")
    
    # Set the UI metadata auth_mode to mcp
    integration.ui_metadata = {"auth_mode": "mcp"}
    db_session.add(integration)
    db_session.commit()

    readiness = service.readiness(integration=integration)

    assert readiness["configured"] is True
    assert readiness["missing"] == []
    assert service._connector_redirect_uri() == "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"


def test_connector_oauth_derives_frontend_redirect_uri_from_public_origin(
    db_session,
    settings,
    monkeypatch,
) -> None:
    settings.averqel_public_origin = "https://averqel.localhost"
    settings.connector_oauth_redirect_uri = (
        "https://averqel.localhost/api/v1/integrations/connectors/oauth/callback"
    )
    settings.connector_oauth_frontend_redirect_uri = None
    monkeypatch.setattr(connector_oauth_service, "MCP_SDK_AVAILABLE", True)

    service = ConnectorOAuthService(db_session, settings)

    # Configure provider client secret to make it configured
    settings.connector_google_oauth_client_id = "google-client-id"
    settings.connector_google_oauth_client_secret = "google-client-secret"
    integration = _seed_integration(db_session, "google-drive")
    
    # Set the UI metadata auth_mode to mcp
    integration.ui_metadata = {"auth_mode": "mcp"}
    db_session.add(integration)
    db_session.commit()

    readiness = service.readiness(integration=integration)

    assert readiness["configured"] is True
    assert readiness["missing"] == []
    assert service._connector_frontend_redirect_uri() == "https://averqel.localhost/dashboard"
