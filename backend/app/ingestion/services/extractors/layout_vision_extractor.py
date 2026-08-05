from __future__ import annotations

from dataclasses import asdict

from app.core.config import Settings
from app.core.errors import ApiError
from app.documents.services.pdf_render_service import PdfRenderService
from app.ingestion.services.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.ingestion.services.ocr_service import OcrService
from app.ingestion.services.vision_service import VisionPageInput, VisionService


class LayoutVisionExtractor(BaseExtractor):
    extraction_method = "layout_vision_fallback"
    supported_extensions = frozenset(
        {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp", ".gif"}
    )
    supported_mime_types = frozenset(
        {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/tiff",
            "image/webp",
            "image/bmp",
            "image/gif",
        }
    )

    def __init__(
        self,
        settings: Settings,
        *,
        vision_service: VisionService | None = None,
        pdf_render_service: PdfRenderService | None = None,
        ocr_service: OcrService | None = None,
    ) -> None:
        self.settings = settings
        self.vision_service = vision_service or VisionService(
            settings=settings, ocr_service=ocr_service
        )
        self.pdf_render_service = pdf_render_service or PdfRenderService(settings)

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        pages = self._build_pages(request)
        vision = self.vision_service.analyze_pages(pages)
        text = "\n\n".join(block.text for block in vision.blocks).strip()
        confidence_values = [block.confidence for block in vision.blocks]
        coverage = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        return ExtractionResult(
            text=text,
            page_count=len(pages),
            extraction_method=self.extraction_method,
            coverage_score=round(min(max(coverage, 0.0), 1.0), 4),
            ocr_used=True,
            vision_used=True,
            warnings=self._dedupe(["vision_layout_fallback_used", *vision.warnings]),
            layout_blocks=[asdict(block) for block in vision.blocks],
        )

    def extract_with_primary(
        self, request: ExtractionRequest, primary: ExtractionResult
    ) -> ExtractionResult:
        try:
            fallback = self.extract(request)
        except ApiError:
            return primary

        merged_text = self._merge_text(primary.text, fallback.text)
        merged_blocks = list(primary.layout_blocks) + list(fallback.layout_blocks)
        merged_warnings = self._dedupe([*primary.warnings, *fallback.warnings])
        coverage = max(primary.coverage_score, fallback.coverage_score)
        return ExtractionResult(
            text=merged_text,
            page_count=primary.page_count or fallback.page_count,
            extraction_method=fallback.extraction_method,
            coverage_score=round(min(max(coverage, 0.0), 1.0), 4),
            ocr_used=primary.ocr_used or fallback.ocr_used,
            vision_used=True,
            warnings=merged_warnings,
            layout_blocks=merged_blocks,
        )

    def _build_pages(self, request: ExtractionRequest) -> list[VisionPageInput]:
        lowered = request.filename.lower()
        if lowered.endswith(".pdf") or request.content_type == "application/pdf":
            rendered_pages = self.pdf_render_service.render_pdf_pages(payload=request.payload)
            return [
                VisionPageInput(page_number=page.page_number, image_bytes=page.image_bytes)
                for page in rendered_pages
            ]

        return [VisionPageInput(page_number=1, image_bytes=request.payload)]

    @staticmethod
    def _merge_text(primary: str, fallback: str) -> str:
        if not primary.strip():
            return fallback.strip()
        if not fallback.strip():
            return primary.strip()
        if fallback.strip() in primary:
            return primary.strip()
        return f"{primary.strip()}\n\n{fallback.strip()}"

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered
