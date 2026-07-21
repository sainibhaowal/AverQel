"""Security checks for user-supplied MCP remote endpoints."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class MCPEndpointRejectedError(ValueError):
    pass


# Backward-compatible name for callers that imported the original exception.
MCPEndpointRejected = MCPEndpointRejectedError

def validate_remote_endpoint(raw: str) -> str:
    value = str(raw or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise MCPEndpointRejectedError("MCP endpoint must be an HTTPS URL without embedded credentials")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal"}:
        raise MCPEndpointRejectedError("MCP endpoint host is not allowed")
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise MCPEndpointRejectedError("MCP endpoint host could not be resolved") from exc
    if any(address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved for address in addresses):
        raise MCPEndpointRejectedError("MCP endpoint resolves to a restricted network")
    return value
