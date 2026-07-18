from __future__ import annotations

from app.services.ingestion.extraction_quality import (
    confidence_band,
    fallback_reasons,
    normalize_warnings,
)
from app.services.ingestion.extractors.base import ExtractionResult


def test_normalize_warnings_dedupes_and_sorts() -> None:
    warnings = [
        " OCR_Low_Confidence ",
        "vision_layout_fallback_used",
        "custom warning",
        "ocr_low_confidence",
    ]
    normalized = normalize_warnings(warnings)
    assert normalized == [
        "ocr_low_confidence",
        "other_custom_warning",
        "vision_layout_fallback_used",
    ]


def test_confidence_band_thresholds() -> None:
    assert confidence_band(0.85) == "high"
    assert confidence_band(0.6) == "medium"
    assert confidence_band(0.2) == "low"
    assert confidence_band(None) == "low"


def test_fallback_reasons_detects_paths() -> None:
    result = ExtractionResult(
        text="x",
        page_count=1,
        extraction_method="pdf_text",
        coverage_score=0.4,
        ocr_used=True,
        vision_used=True,
        warnings=["pdf_ocr_fallback_used", "vision_layout_fallback_used"],
    )
    reasons = fallback_reasons(result)
    assert ("ocr", "pdf_low_coverage") in reasons
    assert ("vision", "layout_complexity") in reasons
