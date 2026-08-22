from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.ingestion.services.ocr_service import OcrService


class _Image:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height


def test_ocr_service_disabled_raises() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.ocr_enabled = False
    service = OcrService(settings)

    with pytest.raises(ApiError) as exc:
        service.extract_image_text(b"x", "a.png")
    assert exc.value.code == "OCR_UNAVAILABLE"


def test_ocr_service_page_limit_enforced() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.ocr_max_pages = 1
    service = OcrService(settings)

    with pytest.raises(ApiError) as exc:
        service.extract_pdf_page_text([b"a", b"b"])
    assert exc.value.code == "OCR_PAGE_LIMIT_EXCEEDED"


def test_ocr_service_dimension_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.ocr_max_image_width = 10
    settings.ocr_max_image_height = 10
    settings.ocr_max_image_pixels = 100
    service = OcrService(settings)

    monkeypatch.setattr(service, "_load_image", lambda payload: _Image(20, 2))

    with pytest.raises(ApiError) as exc:
        service.extract_image_text(b"x", "big.png")
    assert exc.value.code == "IMAGE_PARSE_FAILED"


def test_parse_confidences_filters_invalid_values() -> None:
    values = OcrService._parse_confidences(["92", "-1", "foo", 50])
    assert values == [0.92, 0.5]


def test_parse_confidences_accepts_paddle_scores() -> None:
    values = OcrService._parse_confidences([0.92, 0.5])
    assert values == [0.92, 0.5]


def test_extract_paddle_result_reads_text_and_scores() -> None:
    texts, scores = OcrService._extract_paddle_result(
        [{"res": {"rec_texts": ["Hello", "", "World"], "rec_scores": [0.9, 0.8]}}]
    )
    assert texts == ["Hello", "World"]
    assert scores == [0.9, 0.8]


def test_extract_paddle_result_reads_legacy_ocr_lines() -> None:
    texts, scores = OcrService._extract_paddle_result(
        [[[[(0, 0), (1, 0), (1, 1), (0, 1)], ("Legacy text", 0.87)]]]
    )
    assert texts == ["Legacy text"]
    assert scores == [0.87]
