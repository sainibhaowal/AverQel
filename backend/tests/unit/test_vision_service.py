from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services.ingestion.ocr_service import OcrResult
from app.services.ingestion.vision_service import VisionPageInput, VisionService


class _FakeOcr:
    def extract_image_text(self, payload: bytes, filename: str) -> OcrResult:
        _ = (payload, filename)
        return OcrResult(
            text="1. Overview\nColumn A | Column B\n10 | 20\nThe body paragraph is here.",
            confidence=0.74,
            warnings=[],
            engine="tesseract",
        )


def test_vision_service_disabled_raises() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.vision_enabled = False
    service = VisionService(settings=settings, ocr_service=_FakeOcr())

    with pytest.raises(ApiError) as exc:
        service.analyze_pages([VisionPageInput(page_number=1, image_bytes=b"img")])
    assert exc.value.code == "VISION_UNAVAILABLE"


def test_vision_service_infers_blocks_and_warnings() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.vision_enabled = True
    service = VisionService(settings=settings, ocr_service=_FakeOcr())

    result = service.analyze_pages([VisionPageInput(page_number=1, image_bytes=b"img")])

    assert result.blocks
    assert any(block.block_type == "table" for block in result.blocks)
    assert "table_layout_uncertain" in result.warnings


def test_vision_service_page_limit() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.vision_enabled = True
    settings.vision_max_pages = 1
    service = VisionService(settings=settings, ocr_service=_FakeOcr())

    with pytest.raises(ApiError) as exc:
        service.analyze_pages(
            [
                VisionPageInput(page_number=1, image_bytes=b"img1"),
                VisionPageInput(page_number=2, image_bytes=b"img2"),
            ]
        )
    assert exc.value.code == "VISION_FAILED"
