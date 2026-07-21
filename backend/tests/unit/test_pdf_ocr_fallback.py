from dataclasses import dataclass
from typing import cast

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.documents.services.pdf_render_service import PdfRenderService, RenderedPdfPage
from app.ingestion.services.extractors.base import ExtractionRequest, ExtractionResult
from app.ingestion.services.extractors.layout_vision_extractor import (
    LayoutVisionExtractor,
)
from app.ingestion.services.extractors.pdf_extractor import PdfExtractor
from app.ingestion.services.ocr_service import OcrPageResult, OcrService


@dataclass
class _Page:
    text: str

    def extract_text(self) -> str:
        return self.text


class _Reader:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages


class _FakePdfRender:
    def render_pdf_pages(
        self, *, payload: bytes, page_numbers: list[int] | None = None
    ):
        _ = payload
        numbers = page_numbers or [1]
        return [
            RenderedPdfPage(page_number=n, image_bytes=b"img", width=100, height=100)
            for n in numbers
        ]


class _FakeOcr:
    def extract_pdf_page_text(
        self, images: list[bytes], page_numbers: list[int] | None = None
    ):
        _ = images
        nums = page_numbers or [1]
        return [
            OcrPageResult(
                page_number=nums[0],
                text="Recovered OCR content",
                confidence=0.9,
                warnings=["ocr_page_1_ocr_low_confidence"],
            )
        ]


class _VisionExtractor:
    def extract_with_primary(
        self, request: ExtractionRequest, primary: ExtractionResult
    ) -> ExtractionResult:
        _ = request
        primary.vision_used = True
        primary.warnings.append("vision_layout_fallback_used")
        primary.coverage_score = 0.8
        return primary


def test_pdf_extractor_uses_ocr_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.vision_enabled = False
    monkeypatch.setattr(
        "app.ingestion.services.extractors.pdf_extractor.PdfReader",
        lambda _: _Reader([_Page("")]),
    )

    extractor = PdfExtractor(
        max_pdf_pages=10,
        max_text_chars=5000,
        settings=settings,
        ocr_service=cast(OcrService, _FakeOcr()),
        pdf_render_service=cast(PdfRenderService, _FakePdfRender()),
    )

    result = extractor.extract(
        ExtractionRequest(
            filename="scan.pdf", content_type="application/pdf", payload=b"pdf"
        )
    )

    assert result.ocr_used is True
    assert "pdf_ocr_fallback_used" in result.warnings
    assert "Recovered OCR content" in result.text


def test_pdf_extractor_vision_fallback_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.vision_enabled = True
    settings.extraction_low_coverage_threshold = 0.95
    monkeypatch.setattr(
        "app.ingestion.services.extractors.pdf_extractor.PdfReader",
        lambda _: _Reader([_Page("short")]),
    )

    extractor = PdfExtractor(
        max_pdf_pages=10,
        max_text_chars=5000,
        settings=settings,
        ocr_service=cast(OcrService, _FakeOcr()),
        pdf_render_service=cast(PdfRenderService, _FakePdfRender()),
        vision_extractor=cast(LayoutVisionExtractor, _VisionExtractor()),
    )

    result = extractor.extract(
        ExtractionRequest(
            filename="scan.pdf", content_type="application/pdf", payload=b"pdf"
        )
    )

    assert result.vision_used is True
    assert "vision_layout_fallback_used" in result.warnings


def test_pdf_extractor_handles_unparseable_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings = get_settings()

    def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = (args, kwargs)
        raise RuntimeError("broken")

    monkeypatch.setattr(
        "app.ingestion.services.extractors.pdf_extractor.PdfReader", _raise
    )
    extractor = PdfExtractor(max_pdf_pages=10, max_text_chars=5000, settings=settings)

    with pytest.raises(ApiError) as exc:
        extractor.extract(
            ExtractionRequest(
                filename="bad.pdf", content_type="application/pdf", payload=b"x"
            )
        )
    assert exc.value.code == "PDF_PARSE_FAILED"
