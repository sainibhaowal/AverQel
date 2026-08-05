from __future__ import annotations

import importlib
import time
from typing import Any

from app.providers.services.base import ProviderRequestError
from app.providers.services.types import (
    HealthCheckResult,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResultItem,
)

DEFAULT_TAVILY_BASE_URL = "https://api.tavily.com"
ALLOWED_SEARCH_DEPTHS = {"ultra-fast", "fast", "basic", "advanced"}


class TavilyProvider:
    provider_name = "tavily"

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or DEFAULT_TAVILY_BASE_URL).rstrip("/")
        self.api_key = api_key

    def bind(self, base_url: str | None, api_key: str | None = None) -> TavilyProvider:
        self.base_url = (base_url or DEFAULT_TAVILY_BASE_URL).rstrip("/")
        self.api_key = api_key
        return self

    @staticmethod
    def _httpx(request: WebSearchRequest | None = None) -> Any:
        if request is not None:
            injected = request.metadata.get("httpx_module")
            if injected is not None:
                return injected
        return importlib.import_module("httpx")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=401,
                message="Tavily API key is required.",
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        query = request.query.strip()
        if not query:
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=400,
                message="Search query is required.",
            )
        max_results = max(1, min(int(request.max_results), 10))
        search_depth = (
            request.search_depth if request.search_depth in ALLOWED_SEARCH_DEPTHS else "basic"
        )
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": request.include_answer,
            "include_raw_content": request.include_raw_content,
            "include_favicon": True,
            "include_usage": True,
        }
        topic = request.metadata.get("topic")
        if isinstance(topic, str) and topic in {"general", "news", "finance"}:
            payload["topic"] = topic
        time_range = request.metadata.get("time_range")
        if isinstance(time_range, str) and time_range in {
            "day",
            "week",
            "month",
            "year",
            "d",
            "w",
            "m",
            "y",
        }:
            payload["time_range"] = time_range

        httpx_module = self._httpx(request)
        response = httpx_module.post(
            f"{self.base_url}/search",
            headers=self._headers(),
            json=payload,
            timeout=float(request.timeout_seconds),
        )
        if response.status_code >= 400:
            self._raise_provider_error(response)
        data = response.json()
        if not isinstance(data, dict):
            raise ProviderRequestError(
                provider_name=self.provider_name,
                status_code=502,
                message="Tavily returned an invalid response.",
            )

        results: list[WebSearchResultItem] = []
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            content = item.get("content")
            if (
                not isinstance(title, str)
                or not isinstance(url, str)
                or not isinstance(content, str)
            ):
                continue
            score = item.get("score")
            results.append(
                WebSearchResultItem(
                    title=title.strip(),
                    url=url.strip(),
                    content=content.strip(),
                    score=float(score) if isinstance(score, int | float) else None,
                    raw_content=(
                        item["raw_content"].strip()
                        if isinstance(item.get("raw_content"), str)
                        else None
                    ),
                    favicon=(item.get("favicon") if isinstance(item.get("favicon"), str) else None),
                )
            )

        response_time_raw = data.get("response_time")
        try:
            response_time = float(response_time_raw) if response_time_raw is not None else None
        except (TypeError, ValueError):
            response_time = None
        return WebSearchResponse(
            query=str(data.get("query") or query),
            answer=data.get("answer") if isinstance(data.get("answer"), str) else None,
            results=results,
            response_time=response_time,
            request_id=(
                data.get("request_id") if isinstance(data.get("request_id"), str) else None
            ),
            usage=(dict(data.get("usage") or {}) if isinstance(data.get("usage"), dict) else {}),
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
                    include_raw_content=False,
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

    def _raise_provider_error(self, response: Any) -> None:
        message: str | None = None
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message") or payload.get("error")
            if isinstance(detail, str) and detail.strip():
                message = detail.strip()
        if not message and isinstance(getattr(response, "text", None), str):
            message = response.text.strip() or None
        raise ProviderRequestError(
            provider_name=self.provider_name,
            status_code=int(response.status_code),
            message=message,
        )
