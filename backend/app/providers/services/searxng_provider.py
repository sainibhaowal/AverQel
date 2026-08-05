from __future__ import annotations

import html
import importlib
import ipaddress
import socket
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.core.config import Settings
from app.providers.services.base import ProviderRequestError
from app.providers.services.types import (
    HealthCheckResult,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResultItem,
)

DEFAULT_SEARXNG_BASE_URL = "http://searxng:8080"
MAX_QUERY_LENGTH = 512
MAX_SNIPPET_LENGTH = 2000
BLOCKED_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


def _clean_text(value: object, *, limit: int = MAX_SNIPPET_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    text = html.unescape(value).replace("\x00", " ").strip()
    return " ".join(text.split())[:limit]


def _domain_matches(host: str, domains: object) -> bool:
    if not isinstance(domains, list) or not domains:
        return True
    normalized_host = host.lower().rstrip(".")
    for item in domains:
        if not isinstance(item, str):
            continue
        domain = item.strip().lower().lstrip(".").rstrip(".")
        if domain and (normalized_host == domain or normalized_host.endswith(f".{domain}")):
            return True
    return False


class SearXNGProvider:
    """Server-side SearXNG JSON client with a narrow, safe search surface."""

    provider_name = "searxng"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        settings: Settings | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        del api_key  # SearXNG normally has no API key; auth stays provider-configurable.
        self.base_url = (base_url or DEFAULT_SEARXNG_BASE_URL).rstrip("/")
        self.settings = settings
        self.default_metadata = dict(metadata or {})

    def bind(
        self,
        base_url: str | None,
        api_key: str | None = None,
    ) -> SearXNGProvider:
        del api_key
        self.base_url = (base_url or DEFAULT_SEARXNG_BASE_URL).rstrip("/")
        return self

    @staticmethod
    def _httpx(request: WebSearchRequest | None = None) -> Any:
        if request is not None:
            injected = request.metadata.get("httpx_module")
            if injected is not None:
                return injected
        return importlib.import_module("httpx")

    def _validate_endpoint(self, request: WebSearchRequest) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message="SearXNG endpoint must be a valid http(s) URL.",
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message="SearXNG endpoint must not contain credentials or query data.",
            )

        # Tests can inject a transport. Real requests always resolve and check
        # every address, including DNS rebinding targets.
        if request.metadata.get("httpx_module") is not None:
            return
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="SearXNG endpoint could not be resolved.",
            ) from exc
        for address in addresses:
            raw_ip = address[4][0]
            try:
                ip = ipaddress.ip_address(raw_ip)
            except ValueError as exc:
                raise ProviderRequestError(
                    provider_name=self.provider_name,
                    status_code=502,
                    message="SearXNG endpoint resolved to an invalid address.",
                ) from exc
            if ip in BLOCKED_IPS or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
                raise ProviderRequestError(
                    provider_name=self.provider_name,
                    status_code=403,
                    message="SearXNG endpoint resolves to a blocked network address.",
                )

    def _params(self, request: WebSearchRequest) -> dict[str, str]:
        metadata = request.metadata
        params: dict[str, str] = {
            "q": request.query.strip()[:MAX_QUERY_LENGTH],
            "format": "json",
            "categories": "general",
        }
        language = metadata.get("language")
        if isinstance(language, str) and language.strip():
            params["language"] = language.strip()[:32]
        categories = metadata.get("categories")
        if isinstance(categories, list):
            selected = [str(item).strip() for item in categories if str(item).strip()]
            if selected:
                params["categories"] = ",".join(selected[:5])
        safe_search = metadata.get("safe_search")
        if isinstance(safe_search, int | str) and str(safe_search) in {"0", "1", "2"}:
            params["safesearch"] = str(safe_search)
        time_range = metadata.get("time_range")
        if isinstance(time_range, str) and time_range in {"day", "week", "month", "year"}:
            params["time_range"] = time_range
        return params

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        query = request.query.strip()
        if not query:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message="Search query is required.",
            )
        effective_metadata = {**self.default_metadata, **dict(request.metadata)}
        request = WebSearchRequest(
            query=request.query,
            max_results=request.max_results,
            timeout_seconds=request.timeout_seconds,
            search_depth=request.search_depth,
            include_answer=request.include_answer,
            include_raw_content=request.include_raw_content,
            provider_name=request.provider_name,
            metadata=effective_metadata,
        )
        self._enforce_rate_limit(request)
        self._validate_endpoint(request)

        max_results = max(1, min(int(request.max_results), 10))
        params = self._params(request)
        httpx_module = self._httpx(request)
        timeout = httpx_module.Timeout(
            timeout=float(max(1, min(int(request.timeout_seconds), 30))),
            connect=5.0,
            read=float(max(1, min(int(request.timeout_seconds), 30))),
        )
        try:
            response = httpx_module.get(
                f"{self.base_url}/search",
                params=params,
                headers={"Accept": "application/json", "User-Agent": "AverQel-DeepSpace/1.0"},
                timeout=timeout,
                follow_redirects=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="SearXNG request failed.",
            ) from exc
        if response.status_code >= 400:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=int(response.status_code),
                message="SearXNG returned an error.",
            )
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="SearXNG returned invalid JSON.",
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="SearXNG returned an invalid response.",
            )

        results: list[WebSearchResultItem] = []
        payload_metadata = request.metadata
        allowed_domains = payload_metadata.get("allowed_domains")
        blocked_domains = payload_metadata.get("blocked_domains")
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title"), limit=500)
            url = item.get("url")
            snippet = _clean_text(item.get("content") or item.get("snippet"))
            if not title or not isinstance(url, str) or not snippet:
                continue
            parsed = urlparse(url.strip())
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                continue
            host = parsed.hostname.lower().rstrip(".")
            if not _domain_matches(host, allowed_domains):
                continue
            if isinstance(blocked_domains, list) and _domain_matches(host, blocked_domains):
                continue
            safe_url = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    "",
                    urlencode(parse_qsl(parsed.query, keep_blank_values=True)),
                    "",
                )
            )
            engines = item.get("engines")
            source = (
                ", ".join(str(engine).strip() for engine in engines[:4] if str(engine).strip())
                if isinstance(engines, list)
                else None
            )
            published_date = (
                item.get("publishedDate") or item.get("published_date") or item.get("date")
            )
            score = item.get("score")
            results.append(
                WebSearchResultItem(
                    title=title,
                    url=safe_url,
                    content=snippet,
                    score=float(score) if isinstance(score, int | float) else None,
                    favicon=item.get("img_src") if isinstance(item.get("img_src"), str) else None,
                    published_date=_clean_text(published_date, limit=100) or None,
                    source=_clean_text(source, limit=200) or None,
                )
            )
            if len(results) >= max_results:
                break
        return WebSearchResponse(
            query=query,
            answer=_clean_text(
                payload.get("answers", [None])[0]
                if isinstance(payload.get("answers"), list) and payload.get("answers")
                else None
            )
            or None,
            results=results,
            response_time=None,
            request_id=None,
            usage={"provider": self.provider_name, "result_count": len(results)},
        )

    def _enforce_rate_limit(self, request: WebSearchRequest) -> None:
        limiter_request = request.metadata.get("rate_limit_request")
        tenant_id = str(request.metadata.get("tenant_id") or "unknown")
        user_id = str(request.metadata.get("user_id") or "unknown")
        if self.settings is None or limiter_request is None:
            return
        from app.system.services.rate_limit_service import RateLimitService

        RateLimitService(self.settings).enforce(
            request=limiter_request,
            key=f"rate_limit:deepspace_web_search:{tenant_id}:{user_id}",
            limit=max(1, int(self.settings.rate_limit_queries_per_user_per_minute)),
            window_seconds=60,
            scope="deepspace_web_search",
        )

    def health_check(self) -> HealthCheckResult:
        started = time.monotonic()
        try:
            response = self.search(
                WebSearchRequest(
                    query="test",
                    max_results=1,
                    timeout_seconds=8,
                    include_answer=False,
                    provider_name=self.provider_name,
                )
            )
        except ProviderRequestError as exc:
            return HealthCheckResult(
                status="unhealthy",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="provider_test_failed",
                error_message_redacted=exc.message,
            )
        except Exception as exc:  # noqa: BLE001
            return HealthCheckResult(
                status="unhealthy",
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code="provider_test_failed",
                error_message_redacted=str(exc),
            )
        return HealthCheckResult(
            status="healthy" if response.results else "degraded",
            latency_ms=int((time.monotonic() - started) * 1000),
            metadata={"result_count": len(response.results)},
        )
