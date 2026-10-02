from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class WebhookEndpointError(ValueError):
    pass


def _blocked_address(address: str) -> bool:
    parsed = ipaddress.ip_address(address)
    return bool(
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def validate_webhook_endpoint(
    endpoint_url: str,
    *,
    environment: str,
    resolve_dns: bool = True,
) -> None:
    """Validate an outbound webhook URL and reject server-side request forgery targets."""
    try:
        parsed = urlsplit(endpoint_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise WebhookEndpointError("Webhook endpoint URL is invalid.") from exc
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise WebhookEndpointError("Webhook endpoint must use HTTP or HTTPS.")
    if parsed.username or parsed.password or parsed.fragment:
        raise WebhookEndpointError("Webhook endpoints cannot contain credentials or fragments.")
    if parsed.scheme == "http" and environment not in {"development", "local", "test"}:
        raise WebhookEndpointError("HTTPS is required for production webhook endpoints.")
    if environment in {"development", "local", "test"}:
        return

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host in {"localhost", "localhost.localdomain"}:
        raise WebhookEndpointError("Private or local webhook endpoints are not allowed.")
    try:
        literal = ipaddress.ip_address(normalized_host)
    except ValueError:
        literal = None
    if literal is not None and _blocked_address(str(literal)):
        raise WebhookEndpointError("Private or reserved webhook endpoints are not allowed.")
    if not resolve_dns:
        return
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(
                normalized_host,
                port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as exc:
        raise WebhookEndpointError("Webhook endpoint hostname could not be resolved.") from exc
    if not addresses or any(_blocked_address(address) for address in addresses):
        raise WebhookEndpointError("Webhook endpoint resolves to a private or reserved address.")
