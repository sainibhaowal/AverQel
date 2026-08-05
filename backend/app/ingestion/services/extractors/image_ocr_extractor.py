from __future__ import annotations

from typing import Protocol

from app.core.config import Settings
from app.ingestion.services.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.ingestion.services.ocr_service import OcrResult, OcrService


class OcrClient(Protocol):
    def extract_image_text(self, payload: bytes, filename: str) -> OcrResult: ...


class ImageOcrExtractor(BaseExtractor):
    extraction_method = "image_ocr"
    supported_extensions = frozenset(
        {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp", ".gif"}
    )
    supported_mime_types = frozenset(
        {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/tiff",
            "image/webp",
            "image/bmp",
            "image/gif",
        }
    )

    def __init__(self, settings: Settings, *, ocr_service: OcrClient | None = None) -> None:
        self.settings = settings
        self.ocr_service = ocr_service or OcrService(settings)

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        ocr = self.ocr_service.extract_image_text(
            payload=request.payload, filename=request.filename
        )
        text = ocr.text.strip()
        density_score = min(len(text) / 600.0, 1.0)
        score = max(ocr.confidence, density_score) if text else 0.0
        return ExtractionResult(
            text=text,
            page_count=1,
            extraction_method=self.extraction_method,
            coverage_score=round(min(max(score, 0.0), 1.0), 4),
            ocr_used=True,
            warnings=list(ocr.warnings),
        )
