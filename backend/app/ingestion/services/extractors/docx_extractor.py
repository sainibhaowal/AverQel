from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

from app.core.errors import ApiError
from app.ingestion.services.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.ingestion.services.extractors.office_fallback import extract_openxml_text
from app.ingestion.services.parser_service import sanitize_document_text


class DocxExtractor(BaseExtractor):
    extraction_method = "docx_native"
    supported_extensions = frozenset({".docx"})
    supported_mime_types = frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    )

    def __init__(self, *, max_text_chars: int) -> None:
        self.max_text_chars = max_text_chars

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        constructor = self._load_document_constructor()
        try:
            document = constructor(BytesIO(request.payload))
        except Exception as exc:  # noqa: BLE001
            fallback, source = extract_openxml_text(
                request.payload,
                prefixes=("word/",),
                max_text_chars=self.max_text_chars,
            )
            if fallback is not None and len(fallback) <= self.max_text_chars:
                return ExtractionResult(
                    text=fallback,
                    page_count=None,
                    extraction_method=f"docx_{source or 'fallback'}",
                    coverage_score=0.75,
                    warnings=[f"docx_{source or 'fallback'}"],
                )
            raise ApiError(
                code="DOCX_PARSE_FAILED",
                message="Failed to parse DOCX document.",
                status_code=422,
            ) from exc

        blocks: list[str] = []
        for paragraph in getattr(document, "paragraphs", []):
            text = sanitize_document_text(getattr(paragraph, "text", "")).strip()
            if text:
                blocks.append(text)

        for table in getattr(document, "tables", []):
            for row in getattr(table, "rows", []):
                values: list[str] = []
                for cell in getattr(row, "cells", []):
                    val = sanitize_document_text(getattr(cell, "text", "")).strip()
                    if val:
                        values.append(val)
                if values:
                    blocks.append(" | ".join(values))

        text = "\n".join(blocks).strip()
        if len(text) > self.max_text_chars:
            raise ApiError(
                code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                message="Parsed document exceeds text processing limit.",
                status_code=422,
                details={"max_chars": self.max_text_chars},
            )

        warnings: list[str] = []
        extraction_method = self.extraction_method
        if not text:
            fallback, source = extract_openxml_text(
                request.payload,
                prefixes=("word/",),
                max_text_chars=self.max_text_chars,
            )
            if fallback is not None:
                text = fallback
                warnings.append(f"docx_{source or 'fallback'}")
                extraction_method = f"docx_{source or 'fallback'}"
            else:
                warnings.append("docx_no_text_extracted")
        if len(text) > self.max_text_chars:
            raise ApiError(
                code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                message="Parsed document exceeds text processing limit.",
                status_code=422,
                details={"max_chars": self.max_text_chars},
            )

        return ExtractionResult(
            text=text,
            page_count=None,
            extraction_method=extraction_method,
            coverage_score=1.0 if text else 0.0,
            warnings=warnings,
        )

    def _load_document_constructor(self) -> Callable[[BytesIO], object]:
        try:
            from docx import Document as DocxDocument
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="DOCX_EXTRACTOR_DEPENDENCY_MISSING",
                message="python-docx is required for DOCX extraction.",
                status_code=503,
            ) from exc
        return DocxDocument
