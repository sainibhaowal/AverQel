import pytest

from app.core.errors import ApiError
from app.services.ingestion.extractors.base import ExtractionRequest
from app.services.ingestion.extractors.text_extractors import (
    MarkdownExtractor,
    PlainTextExtractor,
)


def test_markdown_extractor_success():
    extractor = MarkdownExtractor(max_text_chars=1000)
    payload = b"# Hello Target\\nThis is a **markdown** file.\\n"

    req = ExtractionRequest(
        filename="test.md",
        content_type="text/markdown",
        payload=payload,
    )
    result = extractor.extract(req)

    assert result.extraction_method == "markdown_text"
    assert result.coverage_score == 1.0
    assert "Hello Target" in result.text
    assert not result.warnings


def test_markdown_extractor_exceeds_limit():
    extractor = MarkdownExtractor(max_text_chars=10)
    payload = b"This is a very long markdown file."

    req = ExtractionRequest(
        filename="test.md",
        content_type="text/markdown",
        payload=payload,
    )
    with pytest.raises(ApiError) as exc:
        extractor.extract(req)

    assert exc.value.code == "DOCUMENT_TEXT_LIMIT_EXCEEDED"


def test_plaintext_extractor_success():
    extractor = PlainTextExtractor(max_text_chars=1000)
    payload = b"Hello world.\\nNew line.\\n"

    req = ExtractionRequest(
        filename="test.txt",
        content_type="text/plain",
        payload=payload,
    )
    result = extractor.extract(req)

    assert result.extraction_method == "plain_text"
    assert result.coverage_score == 1.0
    assert "Hello world" in result.text
    assert not result.warnings


def test_plaintext_extractor_no_text():
    extractor = PlainTextExtractor(max_text_chars=1000)
    payload = b" "

    req = ExtractionRequest(
        filename="empty.txt",
        content_type="text/plain",
        payload=payload,
    )
    result = extractor.extract(req)

    assert result.coverage_score == 0.0
