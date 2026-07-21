from __future__ import annotations

from app.ingestion.services.extractors.base import ExtractionResult

_KNOWN_WARNING_PREFIXES = (
    "pdf_",
    "ocr_",
    "vision_",
    "legacy_",
    "docx_",
    "pptx_",
    "xlsx_",
    "table_",
    "multi_column_",
    "ipynb_",
    "utf8_",
)


def normalize_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for warning in warnings:
        item = warning.strip().lower().replace(" ", "_")
        if not item:
            continue
        if not item.startswith(_KNOWN_WARNING_PREFIXES):
            item = f"other_{item}"
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    normalized.sort()
    return normalized


def confidence_band(score: float | None) -> str:
    value = float(score or 0.0)
    if value >= 0.8:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"


def fallback_reasons(result: ExtractionResult) -> list[tuple[str, str]]:
    reasons: list[tuple[str, str]] = []
    warning_set = set(result.warnings)
    if result.ocr_used:
        reason = (
            "pdf_low_coverage"
            if "pdf_ocr_fallback_used" in warning_set
            else "image_or_low_text"
        )
        reasons.append(("ocr", reason))
    if result.vision_used:
        reason = (
            "layout_complexity"
            if "vision_layout_fallback_used" in warning_set
            else "low_coverage"
        )
        reasons.append(("vision", reason))
    return reasons
