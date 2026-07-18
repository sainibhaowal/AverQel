from __future__ import annotations

from io import BytesIO
from typing import cast

from pypdf import PdfReader

from app.core.config import Settings
from app.core.errors import ApiError
from app.services.documents.pdf_render_service import PdfRenderService
from app.services.ingestion.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.services.ingestion.extractors.layout_vision_extractor import (
    LayoutVisionExtractor,
)
from app.services.ingestion.ocr_service import OcrPageResult, OcrService
from app.services.ingestion.parser_service import sanitize_document_text


class PdfExtractor(BaseExtractor):
    extraction_method = "pdf_text"
    supported_extensions = frozenset({".pdf"})
    supported_mime_types = frozenset({"application/pdf"})

    def __init__(
        self,
        *,
        max_pdf_pages: int,
        max_text_chars: int,
        settings: Settings,
        ocr_service: OcrService | None = None,
        pdf_render_service: PdfRenderService | None = None,
        vision_extractor: LayoutVisionExtractor | None = None,
    ) -> None:
        self.max_pdf_pages = max_pdf_pages
        self.max_text_chars = max_text_chars
        self.settings = settings
        self.ocr_service = ocr_service or OcrService(settings)
        self.pdf_render = pdf_render_service or PdfRenderService(settings)
        self.vision_extractor = vision_extractor or LayoutVisionExtractor(
            settings=settings,
            ocr_service=cast(OcrService | None, self.ocr_service),
            pdf_render_service=cast(PdfRenderService | None, self.pdf_render),
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        try:
            reader = PdfReader(BytesIO(request.payload))
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
        low_coverage_pages: list[int] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                text = ""
                page_parse_failures += 1
            cleaned = sanitize_document_text(text).strip()
            extracted.append(cleaned)
            if len(cleaned) < 30:
                low_coverage_pages.append(index)

        if page_parse_failures == len(reader.pages) and reader.pages:
            raise ApiError(
                code="PDF_PARSE_FAILED",
                message="Failed to parse PDF document.",
                status_code=422,
            )

        ocr_used = False
        warnings: list[str] = []
        if page_parse_failures:
            warnings.append("pdf_page_extract_partial_failure")

        if low_coverage_pages and self.settings.ocr_enabled:
            ocr_pages = self._ocr_low_coverage_pages(
                payload=request.payload, page_numbers=low_coverage_pages
            )
            ocr_used = bool(ocr_pages)
            for ocr_page in ocr_pages:
                page_idx = ocr_page.page_number - 1
                if ocr_page.text.strip():
                    extracted[page_idx] = sanitize_document_text(ocr_page.text).strip()
                warnings.extend(ocr_page.warnings)
            warnings.append("pdf_ocr_fallback_used")

        full_text = sanitize_document_text("\n".join(extracted)).strip()
        if len(full_text) > self.max_text_chars:
            raise ApiError(
                code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                message="Parsed document exceeds text processing limit.",
                status_code=422,
                details={"max_chars": self.max_text_chars},
            )

        score = min(len(full_text) / 1500.0, 1.0) if full_text else 0.0
        if page_parse_failures:
            score = max(
                0.05,
                (len(reader.pages) - page_parse_failures) / max(len(reader.pages), 1),
            )
        if ocr_used:
            score = max(score, min(len(full_text) / 1200.0, 1.0))

        result = ExtractionResult(
            text=full_text,
            page_count=len(reader.pages),
            extraction_method=self.extraction_method,
            coverage_score=round(score, 4),
            ocr_used=ocr_used,
            warnings=warnings,
        )
        if (
            self.settings.vision_enabled
            and result.coverage_score < self.settings.extraction_low_coverage_threshold
        ):
            return self.vision_extractor.extract_with_primary(request, result)
        return result

    def _ocr_low_coverage_pages(
        self, *, payload: bytes, page_numbers: list[int]
    ) -> list[OcrPageResult]:
        try:
            rendered_pages = self.pdf_render.render_pdf_pages(
                payload=payload, page_numbers=page_numbers
            )
        except ApiError as exc:
            if exc.code in {"OCR_UNAVAILABLE", "OCR_PAGE_LIMIT_EXCEEDED"}:
                return []
            raise

        images = [item.image_bytes for item in rendered_pages]
        indices = [item.page_number for item in rendered_pages]
        try:
            return self.ocr_service.extract_pdf_page_text(images, page_numbers=indices)
        except ApiError as exc:
            if exc.code in {"OCR_UNAVAILABLE", "OCR_TIMEOUT", "OCR_FAILED"}:
                return []
            raise
