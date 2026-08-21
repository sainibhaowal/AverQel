from __future__ import annotations

import base64
import html
import importlib
import ipaddress
import socket
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlparse, urlunparse

from app.providers.services.base import ProviderRequestError

MAX_RESPONSE_BYTES = 2_000_000
MAX_TEXT_CHARS = 40_000
MAX_REDIRECTS = 3
BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}
TEXT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
    "text/markdown",
}


@dataclass(frozen=True, slots=True)
class URLReadResult:
    url: str
    title: str | None
    text: str
    content_type: str
    truncated: bool
    links: list[str]


def _clean_text(value: object, limit: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(value).replace("\x00", " ").split())[:limit]


def validate_public_url(value: str, *, allowed_domains: object = None) -> str:
    parsed = urlparse(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ProviderRequestError(
            "url_reader",
            400,
            "Only public http(s) URLs without credentials are allowed.",
        )
    host = parsed.hostname.rstrip(".").lower()
    if isinstance(allowed_domains, list) and allowed_domains:
        normalized = [
            str(item).strip().lower().lstrip(".") for item in allowed_domains if str(item).strip()
        ]
        if not any(host == domain or host.endswith(f".{domain}") for domain in normalized):
            raise ProviderRequestError(
                "url_reader", 403, "URL domain is outside the configured allowlist."
            )
    try:
        addresses = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ProviderRequestError("url_reader", 502, "URL host could not be resolved.") from exc
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError as exc:
            raise ProviderRequestError(
                "url_reader", 502, "URL host resolved to an invalid address."
            ) from exc
        if (
            ip in BLOCKED_IPS
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ProviderRequestError(
                "url_reader", 403, "Private and link-local URL targets are blocked."
            )
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


def _fetch(
    url: str, *, timeout_seconds: int, max_bytes: int, allowed_domains: object = None
) -> tuple[str, str, bytes]:
    httpx = importlib.import_module("httpx")
    current = validate_public_url(url, allowed_domains=allowed_domains)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(float(max(1, min(timeout_seconds, 30))), connect=5.0),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "GET",
                    current,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,text/plain,application/json,image/*",
                        "User-Agent": "AverQel-DeepSpace/1.0",
                    },
                ) as response:
                    if 300 <= response.status_code < 400:
                        location = response.headers.get("location")
                        if not location:
                            raise ProviderRequestError(
                                "url_reader",
                                502,
                                "URL redirect did not include a location.",
                            )
                        current = validate_public_url(
                            urljoin(current, location), allowed_domains=allowed_domains
                        )
                        continue
                    if response.status_code >= 400:
                        raise ProviderRequestError(
                            "url_reader",
                            int(response.status_code),
                            "URL returned an error.",
                        )
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_length = int(content_length)
                        except ValueError as exc:
                            raise ProviderRequestError(
                                "url_reader",
                                502,
                                "URL returned an invalid content length.",
                            ) from exc
                        if declared_length > max_bytes:
                            raise ProviderRequestError(
                                "url_reader",
                                413,
                                "URL response is larger than the allowed limit.",
                            )
                    chunks: list[bytes] = []
                    received = 0
                    for chunk in response.iter_bytes(64 * 1024):
                        chunks.append(chunk)
                        received += len(chunk)
                        if received > max_bytes:
                            break
                    return (
                        current,
                        response.headers.get("content-type", "application/octet-stream")
                        .split(";", 1)[0]
                        .lower(),
                        b"".join(chunks),
                    )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, ProviderRequestError):
                raise
            raise ProviderRequestError("url_reader", 502, "URL request failed.") from exc
    raise ProviderRequestError("url_reader", 508, "Too many redirects.")


def read_url(
    url: str,
    *,
    timeout_seconds: int = 15,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_domains: object = None,
) -> URLReadResult:
    effective_max_bytes = max(16_384, min(int(max_bytes), MAX_RESPONSE_BYTES))
    final_url, content_type, payload = _fetch(
        url,
        timeout_seconds=timeout_seconds,
        max_bytes=effective_max_bytes,
        allowed_domains=allowed_domains,
    )
    if content_type not in TEXT_TYPES:
        raise ProviderRequestError(
            "url_reader", 415, "URL is not a supported text or JSON document."
        )
    truncated = len(payload) > effective_max_bytes
    raw = payload[:effective_max_bytes].decode("utf-8", errors="replace")
    title = None
    links: list[str] = []
    if content_type in {"text/html", "application/xhtml+xml"}:
        from bs4 import BeautifulSoup
        from bs4.element import Tag

        soup = BeautifulSoup(raw, "html.parser")
        title = _clean_text(soup.title.get_text(" ") if soup.title else "", limit=500) or None
        links = []
        for anchor in soup.find_all("a", href=True)[:20]:
            if not isinstance(anchor, Tag):
                continue
            href = anchor.get("href")
            if isinstance(href, str) and href.strip():
                links.append(urljoin(final_url, href))
        raw = soup.get_text(" ")
    return URLReadResult(final_url, title, _clean_text(raw), content_type, truncated, links)


def read_image(
    url: str,
    *,
    timeout_seconds: int = 15,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_domains: object = None,
) -> dict[str, object]:
    effective_max_bytes = max(16_384, min(int(max_bytes), MAX_RESPONSE_BYTES))
    final_url, content_type, payload = _fetch(
        url,
        timeout_seconds=timeout_seconds,
        max_bytes=effective_max_bytes,
        allowed_domains=allowed_domains,
    )
    if not content_type.startswith("image/"):
        raise ProviderRequestError("image_reader", 415, "URL did not return an image.")
    if len(payload) > effective_max_bytes:
        raise ProviderRequestError("image_reader", 413, "Image is larger than the allowed limit.")
    try:
        from PIL import Image

        image = Image.open(BytesIO(payload))
        width, height = image.size
        image_format = image.format or content_type.split("/", 1)[-1]
    except Exception as exc:  # noqa: BLE001
        raise ProviderRequestError(
            "image_reader", 415, "Image could not be decoded safely."
        ) from exc
    return {
        "url": final_url,
        "content_type": content_type,
        "format": image_format,
        "width": width,
        "height": height,
        "bytes": len(payload),
        # Consumed internally by DeepSpace and removed before tool output is
        # persisted or shown. OpenAI-compatible vision providers can receive it.
        "_image_base64": base64.b64encode(payload).decode("ascii"),
    }
