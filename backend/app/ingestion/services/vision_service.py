from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings
from app.core.errors import ApiError
from app.ingestion.services.ocr_service import OcrResult, OcrService
from app.ingestion.services.parser_service import sanitize_document_text
from app.system.services.metrics_service import observe_extraction_stage


@dataclass(slots=True)
class VisionPageInput:
    page_number: int
    image_bytes: bytes
    hint_text: str = ""


@dataclass(slots=True)
class VisionBlock:
    block_type: str
    text: str
    confidence: float
    page_number: int
    coordinates: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class VisionResult:
    blocks: list[VisionBlock]
    warnings: list[str]
    provider: str


class VisionOcrClient(Protocol):
    def extract_image_text(self, payload: bytes, filename: str) -> OcrResult: ...


class VisionService:
    def __init__(
        self, settings: Settings, *, ocr_service: VisionOcrClient | None = None
    ) -> None:
        self.settings = settings
        self.ocr_service = ocr_service or OcrService(settings)

    def analyze_pages(self, pages: list[VisionPageInput]) -> VisionResult:
        with observe_extraction_stage("vision"):
            if not self.settings.vision_enabled:
                raise ApiError(
                    code="VISION_UNAVAILABLE",
                    message="Vision fallback is disabled in service settings.",
                    status_code=503,
                )
            if len(pages) > self.settings.vision_max_pages:
                raise ApiError(
                    code="VISION_FAILED",
                    message="Vision page processing limit exceeded.",
                    status_code=422,
                    details={"max_pages": self.settings.vision_max_pages},
                )
            if self.settings.vision_provider != "local":
                raise ApiError(
                    code="VISION_UNAVAILABLE",
                    message="Configured vision provider is not available.",
                    status_code=503,
                    details={"provider": self.settings.vision_provider},
                )

            start = time.perf_counter()
            blocks: list[VisionBlock] = []
            warnings: list[str] = []

            for page in pages:
                if time.perf_counter() - start > self.settings.vision_timeout_seconds:
                    raise ApiError(
                        code="VISION_TIMEOUT",
                        message="Vision processing timed out.",
                        status_code=504,
                        details={
                            "timeout_seconds": self.settings.vision_timeout_seconds
                        },
                    )

                raw_text = sanitize_document_text(page.hint_text).strip()
                confidence = 0.0
                if not raw_text:
                    ocr_result = self.ocr_service.extract_image_text(
                        page.image_bytes, filename=f"vision-{page.page_number}.png"
                    )
                    raw_text = ocr_result.text
                    confidence = ocr_result.confidence
                    warnings.extend(ocr_result.warnings)

                page_blocks, page_warnings = self._infer_layout_blocks(
                    text=raw_text,
                    base_confidence=max(
                        confidence, self.settings.vision_min_confidence
                    ),
                    page_number=page.page_number,
                )
                blocks.extend(page_blocks)
                warnings.extend(page_warnings)

            return VisionResult(
                blocks=blocks,
                warnings=self._dedupe(warnings),
                provider=self.settings.vision_provider,
            )

    def _infer_layout_blocks(
        self,
        *,
        text: str,
        base_confidence: float,
        page_number: int,
    ) -> tuple[list[VisionBlock], list[str]]:
        if not text.strip():
            return [], ["vision_no_text_extracted"]

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return [], ["vision_no_text_extracted"]

        blocks: list[VisionBlock] = []
        warnings: list[str] = []

        paragraph_buffer: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph_buffer:
                return
            paragraph = sanitize_document_text(" ".join(paragraph_buffer)).strip()
            if paragraph:
                blocks.append(
                    VisionBlock(
                        block_type="paragraph",
                        text=paragraph,
                        confidence=round(base_confidence, 4),
                        page_number=page_number,
                    )
                )
            paragraph_buffer.clear()

        for line in lines:
            if self._looks_like_table_row(line):
                flush_paragraph()
                blocks.append(
                    VisionBlock(
                        block_type="table",
                        text=line,
                        confidence=round(max(base_confidence - 0.08, 0.0), 4),
                        page_number=page_number,
                    )
                )
                warnings.append("table_layout_uncertain")
                continue

            if self._looks_like_heading(line):
                flush_paragraph()
                blocks.append(
                    VisionBlock(
                        block_type="heading",
                        text=line,
                        confidence=round(min(base_confidence + 0.05, 1.0), 4),
                        page_number=page_number,
                    )
                )
                continue

            paragraph_buffer.append(line)

        flush_paragraph()

        short_line_ratio = sum(1 for line in lines if len(line) < 36) / max(
            len(lines), 1
        )
        if short_line_ratio > 0.45:
            warnings.append("multi_column_reflow_applied")

        return blocks, warnings

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        if len(line) > 120:
            return False
        if re.match(r"^[0-9]+(\.[0-9]+)*\s+", line):
            return True
        title_like = line == line.title() and len(line.split()) <= 12
        upper_like = line.isupper() and len(line.split()) <= 10
        return title_like or upper_like

    @staticmethod
    def _looks_like_table_row(line: str) -> bool:
        return (
            "|" in line
            or "\t" in line
            or bool(re.search(r"\s{2,}", line) and re.search(r"\d", line))
        )

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
