from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

from app.core.errors import ApiError


@dataclass(slots=True)
class ParsedDocument:
    text: str
    page_count: int | None


def sanitize_document_text(value: str) -> str:
    """Remove control bytes unsafe for persistence while preserving readable structure."""
    if not value:
        return ""
    cleaned: list[str] = []
    for ch in value:
        if ch in {"\n", "\r", "\t"}:
            cleaned.append(ch)
            continue
        code = ord(ch)
        if code < 32 or code == 127:
            continue
        cleaned.append(ch)
    return "".join(cleaned)


class ParserService:
    def __init__(
        self, *, max_pdf_pages: int = 1000, max_text_chars: int = 5_000_000
    ) -> None:
        self.max_pdf_pages = max_pdf_pages
        self.max_text_chars = max_text_chars

    def parse_bytes(
        self, *, filename: str, content_type: str, payload: bytes
    ) -> ParsedDocument:
        lowered = filename.lower()
        if content_type == "application/pdf" or lowered.endswith(".pdf"):
            return self._parse_pdf(payload)
        if content_type in {"text/plain", "text/markdown"} or lowered.endswith(
            (".txt", ".md")
        ):
            return self._parse_text(payload)
        raise ApiError(
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported document type for parsing.",
            status_code=400,
        )

    def _parse_pdf(self, payload: bytes) -> ParsedDocument:
        try:
            reader = PdfReader(BytesIO(payload))
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="PDF_PARSE_FAILED",
                message="Failed to parse PDF document.",
                status_code=422,
            ) from exc

        if len(reader.pages) > self.max_pdf_pages:
            raise ApiError(
                code="PDF_PAGE_LIMIT_EXCEEDED",
                message="PDF exceeds page processing limit.",
                status_code=422,
                details={"max_pages": self.max_pdf_pages},
            )

        extracted: list[str] = []
        page_parse_failures = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                text = ""
                page_parse_failures += 1
            extracted.append(sanitize_document_text(text))
        if page_parse_failures == len(reader.pages) and reader.pages:
            raise ApiError(
                code="PDF_PARSE_FAILED",
                message="Failed to parse PDF document.",
                status_code=422,
            )
        full_text = sanitize_document_text("\n".join(extracted)).strip()
        if len(full_text) > self.max_text_chars:
            raise ApiError(
                code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                message="Parsed document exceeds text processing limit.",
                status_code=422,
                details={"max_chars": self.max_text_chars},
            )
        return ParsedDocument(text=full_text, page_count=len(reader.pages))

    def _parse_text(self, payload: bytes) -> ParsedDocument:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            text = payload.decode("utf-8", errors="replace")
        normalized = sanitize_document_text(text).strip()
        if len(normalized) > self.max_text_chars:
            raise ApiError(
                code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                message="Parsed document exceeds text processing limit.",
                status_code=422,
                details={"max_chars": self.max_text_chars},
            )
        return ParsedDocument(text=normalized, page_count=None)
