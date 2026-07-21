from __future__ import annotations

import pytest

from app.core.errors import ApiError
from app.ingestion.services import parser_service
from app.ingestion.services.parser_service import ParserService, sanitize_document_text


def test_parser_handles_text_plain() -> None:
    parser = ParserService()
    parsed = parser.parse_bytes(
        filename="notes.txt",
        content_type="text/plain",
        payload=b"line1\nline2\n",
    )
    assert parsed.page_count is None
    assert "line1" in parsed.text


def test_parser_rejects_unsupported_type() -> None:
    parser = ParserService()
    with pytest.raises(ApiError) as exc_info:
        parser.parse_bytes(
            filename="archive.zip",
            content_type="application/zip",
            payload=b"PK",
        )
    assert exc_info.value.code == "UNSUPPORTED_DOCUMENT_TYPE"


def test_sanitize_document_text_removes_control_bytes() -> None:
    text = "hello\x00world\x07!\nnext\tline\r\n"
    sanitized = sanitize_document_text(text)
    assert "\x00" not in sanitized
    assert "\x07" not in sanitized
    assert "hello" in sanitized
    assert "\n" in sanitized
    assert "\t" in sanitized


def test_parser_text_strips_null_bytes() -> None:
    parser = ParserService()
    parsed = parser.parse_bytes(
        filename="with-null.txt",
        content_type="text/plain",
        payload=b"abc\x00def\n",
    )
    assert parsed.text == "abcdef"


def test_parser_pdf_handles_partial_page_extract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Page:
        def __init__(self, value: str | None = None, *, fail: bool = False) -> None:
            self._value = value
            self._fail = fail

        def extract_text(self) -> str:
            if self._fail:
                raise ValueError("boom")
            return self._value or ""

    class _Reader:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.pages = [_Page("a\x00b"), _Page(fail=True), _Page("c")]

    monkeypatch.setattr(parser_service, "PdfReader", _Reader)
    parser = ParserService()
    parsed = parser.parse_bytes(
        filename="doc.pdf",
        content_type="application/pdf",
        payload=b"%PDF-1.4",
    )
    assert parsed.page_count == 3
    assert parsed.text == "ab\n\nc"


def test_parser_pdf_fails_if_all_pages_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Page:
        def extract_text(self) -> str:
            raise ValueError("boom")

    class _Reader:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.pages = [_Page(), _Page()]

    monkeypatch.setattr(parser_service, "PdfReader", _Reader)
    parser = ParserService()
    with pytest.raises(ApiError) as exc_info:
        parser.parse_bytes(
            filename="doc.pdf",
            content_type="application/pdf",
            payload=b"%PDF-1.4",
        )
    assert exc_info.value.code == "PDF_PARSE_FAILED"
