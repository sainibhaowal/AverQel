from __future__ import annotations

from app.services.providers.tavily_provider import TavilyProvider
from app.services.providers.types import WebSearchRequest


class _FakeResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {
            "query": "latest model news",
            "answer": "A short synthesized answer.",
            "response_time": 0.12,
            "request_id": "req_123",
            "usage": {"searches": 1},
            "results": [
                {
                    "title": "Result One",
                    "url": "https://example.com/one",
                    "content": "Useful web snippet.",
                    "score": 0.91,
                    "favicon": "https://example.com/favicon.ico",
                }
            ],
        }


class _FakeHttpx:
    @staticmethod
    def post(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert args[0] == "https://api.tavily.com/search"
        assert kwargs["headers"]["Authorization"] == "Bearer tvly-test"
        assert kwargs["json"]["max_results"] == 1
        assert kwargs["json"]["include_answer"] is True
        return _FakeResponse()


def test_tavily_provider_parses_search_response() -> None:
    provider = TavilyProvider(api_key="tvly-test")

    response = provider.search(
        WebSearchRequest(
            query="latest model news",
            max_results=1,
            timeout_seconds=5,
            metadata={"httpx_module": _FakeHttpx},
        )
    )

    assert response.answer == "A short synthesized answer."
    assert response.request_id == "req_123"
    assert response.results[0].title == "Result One"
    assert response.results[0].url == "https://example.com/one"
