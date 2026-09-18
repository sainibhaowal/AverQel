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
    return len(text) < 200 and not result.links and not result.section_headings


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
        if exc.status_code in {400, 403} or not browser_enabled:
            raise
        static_error = exc
    else:
        if not browser_enabled or not _needs_browser_fallback(result):
            return result
        try:
            return read_rendered_url(
                result.url,
                settings=settings,
                allowed_domains=allowed_domains,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
            )
        except ProviderRequestError:
            return result

    try:
        return read_rendered_url(
            url,
            settings=settings,
            allowed_domains=allowed_domains,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
        )
    except ProviderRequestError as browser_error:
        if static_error is not None:
            raise static_error from browser_error
        raise
