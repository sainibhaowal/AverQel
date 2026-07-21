from __future__ import annotations

from app.ingestion.services.extraction_quality import fallback_reasons
from app.ingestion.services.extractors.base import ExtractionResult
from app.services.system.metrics_service import (
    EXTRACTION_FAILURE_TOTAL,
    EXTRACTION_FALLBACK_TOTAL,
    EXTRACTION_LOW_CONFIDENCE_TOTAL,
    EXTRACTION_METHOD_TOTAL,
    EXTRACTION_STAGE_DURATION_SECONDS,
    observe_extraction_stage,
)


def test_extraction_method_total_emits() -> None:
    before = EXTRACTION_METHOD_TOTAL.labels(method="test_method")._value.get()
    EXTRACTION_METHOD_TOTAL.labels(method="test_method").inc()
    after = EXTRACTION_METHOD_TOTAL.labels(method="test_method")._value.get()
    assert after == before + 1


def test_extraction_fallback_total_emits() -> None:
    result = ExtractionResult(
        text="x",
        page_count=1,
        extraction_method="pdf_text",
        coverage_score=0.4,
        ocr_used=True,
        vision_used=True,
        warnings=["pdf_ocr_fallback_used", "vision_layout_fallback_used"],
    )
    for path, reason in fallback_reasons(result):
        before = EXTRACTION_FALLBACK_TOTAL.labels(path=path, reason=reason)._value.get()
        EXTRACTION_FALLBACK_TOTAL.labels(path=path, reason=reason).inc()
        after = EXTRACTION_FALLBACK_TOTAL.labels(path=path, reason=reason)._value.get()
        assert after == before + 1


def test_extraction_low_confidence_total_emits() -> None:
    before = EXTRACTION_LOW_CONFIDENCE_TOTAL.labels(band="low")._value.get()
    EXTRACTION_LOW_CONFIDENCE_TOTAL.labels(band="low").inc()
    after = EXTRACTION_LOW_CONFIDENCE_TOTAL.labels(band="low")._value.get()
    assert after == before + 1


def test_extraction_failure_total_emits() -> None:
    before = EXTRACTION_FAILURE_TOTAL.labels(code="TEST_ERROR")._value.get()
    EXTRACTION_FAILURE_TOTAL.labels(code="TEST_ERROR").inc()
    after = EXTRACTION_FAILURE_TOTAL.labels(code="TEST_ERROR")._value.get()
    assert after == before + 1


def test_observe_extraction_stage_records_duration() -> None:
    # Safely get count with sample extraction

    def get_count() -> float:
        for m in EXTRACTION_STAGE_DURATION_SECONDS.collect():
            for sample in m.samples:
                if (
                    sample.name == "aks_extraction_stage_duration_seconds_count"
                    and sample.labels.get("stage") == "test_stage"
                ):
                    return sample.value
        return 0.0

    before_val = get_count()
    with observe_extraction_stage("test_stage"):
        pass
    after_val = get_count()
    assert after_val == before_val + 1
