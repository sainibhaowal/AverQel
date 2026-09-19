from types import SimpleNamespace

import pytest

from app.deepspace.services import browser_reader
from app.deepspace.services.url_reader import URLReadResult
from app.providers.services.base import ProviderRequestError


def _result(**overrides: object) -> URLReadResult:
    values: dict[str, object] = {
        "url": "https://example.com/app",
        "title": "App",
        "text": "",
        "content_type": "text/html",
        "truncated": False,
        "links": [],
        "section_headings": [],
    }
    values.update(overrides)
    return URLReadResult(**values)


def test_js_shell_uses_browser_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser_reader, "read_url", lambda *args, **kwargs: _result())
    calls: list[dict[str, object]] = []

    def render(url: str, **kwargs: object) -> URLReadResult:
        calls.append({"url": url, **kwargs})
        return _result(
            title="Rendered App",
            text="The page content was rendered after JavaScript executed.",
            retrieval_method="browser_renderer",
        )

    monkeypatch.setattr(browser_reader, "read_rendered_url", render)

    result = browser_reader.read_url_with_browser_fallback(
        "https://example.com/app",
        settings=SimpleNamespace(deepspace_research_browser_enabled=True),
    )

    assert result.retrieval_method == "browser_renderer"
    assert result.title == "Rendered App"
    assert calls[0]["url"] == "https://example.com/app"


def test_remote_http_403_uses_browser_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        browser_reader,
        "read_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProviderRequestError("url_reader", 403, "URL returned HTTP 403.")
        ),
    )
    monkeypatch.setattr(
        browser_reader,
        "read_rendered_url",
        lambda *args, **kwargs: _result(
            title="Rendered page",
            text="The browser renderer fetched the public page.",
            retrieval_method="browser_renderer",
        ),
    )

    result = browser_reader.read_url_with_browser_fallback(
        "https://example.com/blocked-to-static-reader",
        settings=SimpleNamespace(deepspace_research_browser_enabled=True),
    )

    assert result.retrieval_method == "browser_renderer"


def test_browser_challenge_is_not_reported_as_page_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        browser_reader,
        "read_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProviderRequestError("url_reader", 403, "URL returned HTTP 403.")
        ),
    )
    monkeypatch.setattr(
        browser_reader,
        "read_rendered_url",
        lambda *args, **kwargs: _result(text="Enable JavaScript and cookies to continue"),
    )

    with pytest.raises(ProviderRequestError, match="anti-bot challenge"):
        browser_reader.read_url_with_browser_fallback(
            "https://example.com/protected",
            settings=SimpleNamespace(deepspace_research_browser_enabled=True),
        )


def test_useful_static_page_does_not_start_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    static = _result(
        text="A useful static article with enough content to answer the question.",
        section_headings=["Article"],
    )
    monkeypatch.setattr(browser_reader, "read_url", lambda *args, **kwargs: static)

    def should_not_render(*args: object, **kwargs: object) -> URLReadResult:
        raise AssertionError("browser should not run for useful static content")

    monkeypatch.setattr(browser_reader, "read_rendered_url", should_not_render)

    assert (
        browser_reader.read_url_with_browser_fallback(
            static.url,
            settings=SimpleNamespace(deepspace_research_browser_enabled=True),
        )
        is static
    )


def test_browser_fallback_never_bypasses_blocked_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        browser_reader,
        "read_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProviderRequestError(
                "url_reader", 403, "Private and link-local URL targets are blocked."
            )
        ),
    )
    monkeypatch.setattr(
        browser_reader,
        "read_rendered_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("blocked URL was rendered")),
    )

    with pytest.raises(ProviderRequestError, match="Private"):
        browser_reader.read_url_with_browser_fallback(
            "https://127.0.0.1/private",
            settings=SimpleNamespace(deepspace_research_browser_enabled=True),
        )
