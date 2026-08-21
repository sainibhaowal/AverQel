import pytest

from app.deepspace.services import url_reader
from app.providers.services.base import ProviderRequestError


def test_validate_public_url_enforces_scheme_allowlist_and_dns(monkeypatch) -> None:
    monkeypatch.setattr(
        url_reader.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    assert (
        url_reader.validate_public_url("https://example.com/a?x=1", allowed_domains=["example.com"])
        == "https://example.com/a?x=1"
    )
    for value in (
        "file:///tmp/a",
        "https://user:pass@example.com",
        "https://other.test",
    ):
        with pytest.raises(ProviderRequestError):
            url_reader.validate_public_url(value, allowed_domains=["example.com"])


def test_validate_public_url_blocks_private_and_unresolvable_hosts(monkeypatch) -> None:
    monkeypatch.setattr(
        url_reader.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("127.0.0.1", 0))],
    )
    with pytest.raises(ProviderRequestError):
        url_reader.validate_public_url("http://localhost")

    def fail_dns(*_args, **_kwargs):
        raise OSError("dns failure")

    monkeypatch.setattr(url_reader.socket, "getaddrinfo", fail_dns)
    with pytest.raises(ProviderRequestError):
        url_reader.validate_public_url("https://example.com")


def test_read_url_parses_html_and_read_image_rejects_non_image(monkeypatch) -> None:
    monkeypatch.setattr(
        url_reader,
        "_fetch",
        lambda *_args, **_kwargs: (
            "https://example.com/page",
            "text/html",
            b"<html><title>Title</title><a href='/next'>Next</a><p>Hello world</p></html>",
        ),
    )
    result = url_reader.read_url("https://example.com/page")
    assert result.title == "Title"
    assert result.text == "Title Next Hello world"
    assert result.links == ["https://example.com/next"]

    monkeypatch.setattr(
        url_reader,
        "_fetch",
        lambda *_args, **_kwargs: (
            "https://example.com/file",
            "text/plain",
            b"not image",
        ),
    )
    with pytest.raises(ProviderRequestError):
        url_reader.read_image("https://example.com/file")
