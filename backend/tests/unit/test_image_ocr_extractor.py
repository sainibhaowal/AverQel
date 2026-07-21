from __future__ import annotations

from app.core.config import get_settings
from app.ingestion.services.extractors.base import ExtractionRequest
from app.ingestion.services.extractors.image_ocr_extractor import ImageOcrExtractor
from app.ingestion.services.ocr_service import OcrResult


class _FakeOcrService:
    def extract_image_text(self, payload: bytes, filename: str) -> OcrResult:
        _ = (payload, filename)
        return OcrResult(
            text="Detected text from image",
            confidence=0.88,
            warnings=["ocr_low_confidence"],
            engine="tesseract",
        )


def test_image_ocr_extractor_maps_contract() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    extractor = ImageOcrExtractor(settings=settings, ocr_service=_FakeOcrService())

    result = extractor.extract(
        ExtractionRequest(filename="scan.png", content_type="image/png", payload=b"img")
    )

    assert result.extraction_method == "image_ocr"
    assert result.ocr_used is True
    assert result.coverage_score >= 0.88
    assert "ocr_low_confidence" in result.warnings
    assert result.text.startswith("Detected")
