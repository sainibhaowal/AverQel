from __future__ import annotations

import socket

import pytest

from app.documents.services.webhook_security import WebhookEndpointError, validate_webhook_endpoint


def test_development_allows_local_endpoint_for_local_testing() -> None:
    validate_webhook_endpoint("http://127.0.0.1:9000/events", environment="development")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1/events",
        "https://10.0.0.8/events",
        "https://[::1]/events",
        "https://localhost/events",
    ],
)
def test_production_rejects_private_and_local_targets(endpoint: str) -> None:
    with pytest.raises(WebhookEndpointError):
        validate_webhook_endpoint(endpoint, environment="production")


def test_production_rejects_http_even_for_public_host() -> None:
    with pytest.raises(WebhookEndpointError, match="HTTPS"):
        validate_webhook_endpoint("http://example.com/events", environment="production")


def test_production_rejects_dns_that_resolves_to_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))
        ],
    )
    with pytest.raises(WebhookEndpointError, match="private"):
        validate_webhook_endpoint("https://events.example.com/events", environment="production")


def test_production_rejects_credentials_and_fragments() -> None:
    with pytest.raises(WebhookEndpointError):
        validate_webhook_endpoint(
            "https://user:password@example.com/events", environment="production"
        )
    with pytest.raises(WebhookEndpointError):
        validate_webhook_endpoint("https://example.com/events#secret", environment="production")


def test_public_hostname_can_be_checked_without_network_in_unit_tests() -> None:
    validate_webhook_endpoint(
        "https://events.example.com/events", environment="production", resolve_dns=False
    )
