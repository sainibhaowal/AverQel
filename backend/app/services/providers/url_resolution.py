from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse, urlunparse


def _running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _is_loopback_host(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:  # nosec B104
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def resolve_provider_base_url(
    base_url: str | None, *, provider_type: str | None = None
) -> str | None:
    del provider_type
    if base_url is None:
        return None

    cleaned = base_url.strip()
    if not cleaned:
        return cleaned

    if not _running_in_docker():
        return cleaned.rstrip("/")

    parsed = urlparse(cleaned)
    if not _is_loopback_host(parsed.hostname or ""):
        # If user provided a non-loopback URL (like 192.168.0.10), use it as-is
        return cleaned.rstrip("/")

    # For localhost URLs in Docker:
    # - On Linux, host.docker.internal may not work reliably
    # - Use it anyway (user can override with actual IP if needed)
    # - On Mac/Windows Docker Desktop, it works fine
    netloc = "host.docker.internal"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"

    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials = f"{credentials}:{parsed.password}"
        netloc = f"{credentials}@{netloc}"

    return urlunparse(parsed._replace(netloc=netloc)).rstrip("/")
