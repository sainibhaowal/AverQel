from __future__ import annotations

from app.providers.services.searxng_provider import SearXNGProvider
from app.providers.services.types import WebSearchRequest


class _FakeResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {
            "results": [
                {
                    "title": "Allowed result",
                    "url": "https://docs.example.com/guide?utm_source=test#fragment",
                    "content": "A useful <b>search</b> snippet.",
                    "publishedDate": "2026-07-26",
                    "engines": ["google", "brave"],
                },
                {
                    "title": "Blocked result",
                    "url": "https://blocked.example.org/item",
                    "content": "This must not pass the configured domain policy.",
                },
            ]
        }


class _FakeTimeout:
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        pass


class _FakeHttpx:
    Timeout = _FakeTimeout

    @staticmethod
    def get(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert args[0] == "http://search.internal/search"
        assert kwargs["params"]["format"] == "json"
        assert kwargs["follow_redirects"] is False
        return _FakeResponse()


def test_searxng_provider_parses_and_filters_results() -> None:
    provider = SearXNGProvider(
        base_url="http://search.internal",
        metadata={"allowed_domains": ["example.com"]},
    )

    response = provider.search(
        WebSearchRequest(
            query="latest research",
            max_results=5,
            timeout_seconds=5,
            metadata={"httpx_module": _FakeHttpx},
        )
    )

    assert len(response.results) == 1
    assert response.results[0].title == "Allowed result"
    assert response.results[0].published_date == "2026-07-26"
    assert response.results[0].source == "google, brave"
    assert "#fragment" not in response.results[0].url


def test_searxng_provider_rejects_unsafe_endpoint() -> None:
    provider = SearXNGProvider(base_url="http://169.254.169.254:80")
    try:
        provider.search(WebSearchRequest(query="test", max_results=1, timeout_seconds=5))
    except Exception as exc:  # noqa: BLE001
        assert "blocked" in str(exc).lower()
    else:
        raise AssertionError("unsafe SearXNG endpoint was accepted")
