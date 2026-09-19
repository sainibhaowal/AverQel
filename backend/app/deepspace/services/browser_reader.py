"""Optional isolated browser fallback for JavaScript-rendered public pages.

It is off by default. The caller validates the public target before this
module contacts a separately deployed renderer; no browser endpoint, cookies,
credentials, or private-network URL is accepted from a user/model.
"""

from __future__ import annotations

import importlib
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.deepspace.services.url_reader import (
    MAX_RESPONSE_BYTES,
    URLReadResult,
    _clean_text,
    read_url,
    validate_public_url,
)
from app.providers.services.base import ProviderRequestError


def _is_url_security_error(error: ProviderRequestError) -> bool:
    """Keep validation failures from being retried through another network path."""

    return error.status_code == 400 or (
        error.status_code == 403
        and error.message
        in {
            "URL domain is outside the configured allowlist.",
            "Private and link-local URL targets are blocked.",
        }
    )


def _is_automated_access_challenge(result: URLReadResult) -> bool:
    """Reject Cloudflare/anti-bot interstitials as page content."""

    content = f"{result.title or ''} {result.text}".casefold()
    return any(
        marker in content
        for marker in (
            "enable javascript and cookies to continue",
            "just a moment...",
            "checking your browser",
            "verify you are human",
            "attention required! | cloudflare",
        )
    )


def read_rendered_url(
    url: str,
    *,
    settings: Any,
    allowed_domains: object = None,
    timeout_seconds: int = 15,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> URLReadResult:
    endpoint = str(getattr(settings, "deepspace_research_browser_url", "") or "").rstrip("/")
    if not bool(getattr(settings, "deepspace_research_browser_enabled", False)) or not endpoint:
        raise ProviderRequestError(
            "browser_reader", 503, "Isolated browser rendering is not enabled."
        )
    target = validate_public_url(url, allowed_domains=allowed_domains)
    httpx = importlib.import_module("httpx")
    token = str(getattr(settings, "deepspace_research_browser_token", "") or "")
    parsed_endpoint = urlsplit(endpoint)
    content_endpoint = urlunsplit(
        (
            parsed_endpoint.scheme,
            parsed_endpoint.netloc,
            f"{parsed_endpoint.path.rstrip('/')}/content",
            parsed_endpoint.query,
            "",
        )
    )
    headers = {"Accept": "text/html", "User-Agent": "AverQel-Research/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        effective_timeout = max(5, min(int(timeout_seconds), 30))
        effective_max_bytes = max(16_384, min(int(max_bytes), MAX_RESPONSE_BYTES))
        response = httpx.post(
            content_endpoint,
            json={
                "url": target,
                "gotoOptions": {"waitUntil": "domcontentloaded", "timeout": 15_000},
            },
            headers=headers,
            timeout=httpx.Timeout(float(effective_timeout), connect=5.0),
            follow_redirects=False,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ProviderRequestError(
            "browser_reader", 502, "Isolated browser render failed."
        ) from exc
    payload = response.content
    effective_max_bytes = max(16_384, min(int(max_bytes), MAX_RESPONSE_BYTES))
    truncated = len(payload) > effective_max_bytes
    html = payload[:effective_max_bytes].decode("utf-8", errors="replace")
    try:
        from bs4 import BeautifulSoup
        from bs4.element import Tag

        soup = BeautifulSoup(html, "html.parser")
        title = _clean_text(soup.title.get_text(" ") if soup.title else "", limit=500) or None
        text = _clean_text(soup.get_text(" "))
        headings = [
            _clean_text(node.get_text(" "), limit=300)
            for node in soup.find_all(["h1", "h2", "h3"])[:30]
            if isinstance(node, Tag)
        ]
        links = [
            urljoin(target, str(node.get("href")))
            for node in soup.find_all("a", href=True)[:20]
            if isinstance(node, Tag)
            and str(node.get("href") or "").startswith(("https://", "/", "#"))
        ]
    except Exception as exc:  # noqa: BLE001
        raise ProviderRequestError(
            "browser_reader", 502, "Browser returned unreadable content."
        ) from exc
    return URLReadResult(
        target,
        title,
        text,
        "text/html",
        truncated,
        links,
        section_headings=[item for item in headings if item],
        retrieval_method="browser_renderer",
    )


def _needs_browser_fallback(result: URLReadResult) -> bool:
    """Detect the common empty-shell response from a JavaScript application."""

    if result.content_type not in {"text/html", "application/xhtml+xml"}:
        return False
    text = result.text.strip()
    return _is_automated_access_challenge(result) or (
        len(text) < 200 and not result.links and not result.section_headings
    )


def read_url_with_browser_fallback(
    url: str,
    *,
    settings: Any,
    timeout_seconds: int = 15,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_domains: object = None,
) -> URLReadResult:
    """Read a page statically, using isolated Chromium only for JS shells."""

    browser_enabled = bool(getattr(settings, "deepspace_research_browser_enabled", False))
    static_error: ProviderRequestError | None = None
    try:
        result = read_url(
            url,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            allowed_domains=allowed_domains,
        )
    except ProviderRequestError as exc:
        if _is_url_security_error(exc) or not browser_enabled:
            raise
        static_error = exc
    else:
        if not browser_enabled or not _needs_browser_fallback(result):
            return result
        try:
            rendered = read_rendered_url(
                result.url,
                settings=settings,
                allowed_domains=allowed_domains,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
            )
            if _is_automated_access_challenge(rendered):
                raise ProviderRequestError(
                    "browser_reader",
                    403,
                    "The public page blocked automated access with an anti-bot challenge.",
                )
            return rendered
        except ProviderRequestError:
            if result.text.strip() and not _is_automated_access_challenge(result):
                return result
            raise

    try:
        rendered = read_rendered_url(
            url,
            settings=settings,
            allowed_domains=allowed_domains,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
        )
        if _is_automated_access_challenge(rendered):
            raise ProviderRequestError(
                "browser_reader",
                403,
                "The public page blocked automated access with an anti-bot challenge.",
            )
        return rendered
    except ProviderRequestError as browser_error:
        if static_error is not None:
            raise browser_error from static_error
        raise
