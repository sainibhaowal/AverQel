from __future__ import annotations

from app.core.errors import ApiError
from app.services.ingestion.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.services.ingestion.parser_service import sanitize_document_text


class PlainTextExtractor(BaseExtractor):
    extraction_method = "plain_text"
    supported_extensions = frozenset({".txt"})
    supported_mime_types = frozenset({"text/plain"})

    def __init__(self, *, max_text_chars: int) -> None:
        self.max_text_chars = max_text_chars

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return _decode_text_payload(
            request=request,
            max_text_chars=self.max_text_chars,
            extraction_method=self.extraction_method,
        )


class MarkdownExtractor(BaseExtractor):
    extraction_method = "markdown_text"
    supported_extensions = frozenset({".md"})
    supported_mime_types = frozenset({"text/markdown", "text/x-markdown"})

    def __init__(self, *, max_text_chars: int) -> None:
        self.max_text_chars = max_text_chars

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return _decode_text_payload(
            request=request,
            max_text_chars=self.max_text_chars,
            extraction_method=self.extraction_method,
        )


class CodeTextExtractor(BaseExtractor):
    extraction_method = "code_text"
    supported_extensions = frozenset(
        {
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".cs",
            ".php",
            ".rb",
            ".swift",
            ".kt",
            ".scala",
            ".sql",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".sh",
            ".toml",
            ".ini",
            ".cfg",
            ".log",
            ".csv",
            ".tsv",
            ".ipynb",
        }
    )
    supported_mime_types = frozenset(
        {
            "text/plain",
            "application/json",
            "application/xml",
            "text/xml",
            "text/csv",
            "text/tab-separated-values",
            "application/x-sh",
            "text/x-python",
            "application/octet-stream",
            "application/x-ipynb+json",
        }
    )

    def __init__(self, *, max_text_chars: int) -> None:
        self.max_text_chars = max_text_chars

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        result = _decode_text_payload(
            request=request,
            max_text_chars=self.max_text_chars,
            extraction_method=self.extraction_method,
        )
        if request.filename.lower().endswith(".ipynb"):
            result.warnings.append("ipynb_flat_text_extraction")
        return result


def _decode_text_payload(
    *,
    request: ExtractionRequest,
    max_text_chars: int,
    extraction_method: str,
) -> ExtractionResult:
    try:
        text = request.payload.decode("utf-8")
        warnings: list[str] = []
    except UnicodeDecodeError:
        text = request.payload.decode("utf-8", errors="replace")
        warnings = ["utf8_decode_replacement"]

    normalized = sanitize_document_text(text).strip()
    if len(normalized) > max_text_chars:
        raise ApiError(
            code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
            message="Parsed document exceeds text processing limit.",
            status_code=422,
            details={"max_chars": max_text_chars},
        )

    score = 1.0 if normalized else 0.0
    return ExtractionResult(
        text=normalized,
        page_count=None,
        extraction_method=extraction_method,
        coverage_score=score,
        warnings=warnings,
    )
