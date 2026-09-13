"""Optional isolated browser fallback for JavaScript-rendered public pages.

It is off by default. The caller validates the public target before this
module contacts a separately deployed renderer; no browser endpoint, cookies,
credentials, or private-network URL is accepted from a user/model.
"""

from __future__ import annotations

import importlib
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.deepspace.services.url_reader import URLReadResult, _clean_text, validate_public_url
from app.providers.services.base import ProviderRequestError


def read_rendered_url(url: str, *, settings: Any, allowed_domains: object = None) -> URLReadResult:
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
        response = httpx.post(
            content_endpoint,
            json={
                "url": target,
                "gotoOptions": {"waitUntil": "domcontentloaded", "timeout": 15_000},
            },
            headers=headers,
            timeout=httpx.Timeout(20.0, connect=5.0),
            follow_redirects=False,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ProviderRequestError(
            "browser_reader", 502, "Isolated browser render failed."
        ) from exc
    html = response.text[:2_000_000]
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        title = _clean_text(soup.title.get_text(" ") if soup.title else "", limit=500) or None
        text = _clean_text(soup.get_text(" "))
        headings = [
            _clean_text(node.get_text(" "), limit=300)
            for node in soup.find_all(["h1", "h2", "h3"])[:30]
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
        len(response.text) > len(html),
        [],
        section_headings=[item for item in headings if item],
    )
