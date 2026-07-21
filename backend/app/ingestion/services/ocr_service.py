from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from app.core.config import Settings
from app.core.errors import ApiError
from app.ingestion.services.parser_service import sanitize_document_text
from app.services.system.metrics_service import observe_extraction_stage


@dataclass(slots=True)
class OcrResult:
    text: str
    confidence: float
    warnings: list[str] = field(default_factory=list)
    engine: str = ""


@dataclass(slots=True)
class OcrPageResult:
    page_number: int
    text: str
    confidence: float
    warnings: list[str] = field(default_factory=list)


class OcrService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract_image_text(self, payload: bytes, filename: str) -> OcrResult:
        with observe_extraction_stage("ocr"):
            if not self.settings.ocr_enabled:
                raise ApiError(
                    code="OCR_UNAVAILABLE",
                    message="OCR is disabled in service settings.",
                    status_code=503,
                )

            if self.settings.ocr_engine == "tesseract":
                return self._extract_with_tesseract(payload=payload, filename=filename)

            raise ApiError(
                code="OCR_UNAVAILABLE",
                message="Configured OCR engine is not available.",
                status_code=503,
                details={"engine": self.settings.ocr_engine},
            )

    def extract_pdf_page_text(
        self, images: list[bytes], page_numbers: list[int] | None = None
    ) -> list[OcrPageResult]:
        if len(images) > self.settings.ocr_max_pages:
            raise ApiError(
                code="OCR_PAGE_LIMIT_EXCEEDED",
                message="OCR page processing limit exceeded.",
                status_code=422,
                details={"max_pages": self.settings.ocr_max_pages},
            )

        results: list[OcrPageResult] = []
        indices = page_numbers or [index + 1 for index in range(len(images))]
        for page_number, image_payload in zip(indices, images, strict=True):
            page_result = self.extract_image_text(
                image_payload, filename=f"page-{page_number}.png"
            )
            page_warnings = [
                f"ocr_page_{page_number}_{warning}" for warning in page_result.warnings
            ]
            results.append(
                OcrPageResult(
                    page_number=page_number,
                    text=page_result.text,
                    confidence=page_result.confidence,
                    warnings=page_warnings,
                )
            )
        return results

    def _extract_with_tesseract(self, *, payload: bytes, filename: str) -> OcrResult:
        image = self._load_image(payload=payload)
        self._guard_dimensions(image.width, image.height)

        try:
            import pytesseract  # type: ignore[import-not-found, import-untyped]
            from pytesseract import Output  # type: ignore[import-not-found, import-untyped]
            from pytesseract.pytesseract import (  # type: ignore[import-not-found, import-untyped]
                TesseractNotFoundError,
            )
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="OCR_UNAVAILABLE",
                message="pytesseract is required for OCR extraction.",
                status_code=503,
            ) from exc

        lang = "+".join(self.settings.ocr_languages)
        attempts = max(self.settings.ocr_retry_attempts, 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                data = pytesseract.image_to_data(
                    image,
                    lang=lang,
                    output_type=Output.DICT,
                    timeout=self.settings.ocr_timeout_seconds,
                )
                words = [
                    sanitize_document_text(word).strip()
                    for word in data.get("text", [])
                ]
                confidence_values = self._parse_confidences(data.get("conf", []))
                extracted_words = [word for word in words if word]
                text = sanitize_document_text(" ".join(extracted_words)).strip()
                confidence = (
                    statistics.fmean(confidence_values) if confidence_values else 0.0
                )
                warnings: list[str] = []
                if confidence < self.settings.ocr_min_confidence:
                    warnings.append("ocr_low_confidence")
                if not text:
                    warnings.append("ocr_no_text_extracted")
                return OcrResult(
                    text=text,
                    confidence=round(min(max(confidence, 0.0), 1.0), 4),
                    warnings=warnings,
                    engine="tesseract",
                )
            except TesseractNotFoundError as exc:
                raise ApiError(
                    code="OCR_UNAVAILABLE",
                    message="Tesseract binary is not available.",
                    status_code=503,
                ) from exc
            except RuntimeError as exc:
                if "time" in str(exc).lower():
                    raise ApiError(
                        code="OCR_TIMEOUT",
                        message="OCR processing timed out.",
                        status_code=504,
                        details={"timeout_seconds": self.settings.ocr_timeout_seconds},
                    ) from exc
                last_error = exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc

            if attempt < attempts:
                time.sleep(min(0.25 * attempt, 1.0))

        raise ApiError(
            code="OCR_FAILED",
            message="OCR extraction failed.",
            status_code=422,
            details={"filename": filename},
        ) from last_error

    def _load_image(self, *, payload: bytes) -> Any:
        try:
            from PIL import Image
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="OCR_UNAVAILABLE",
                message="Pillow is required for OCR image decoding.",
                status_code=503,
            ) from exc

        try:
            image = Image.open(BytesIO(payload))
            image.load()
            return image
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="IMAGE_PARSE_FAILED",
                message="Failed to parse image payload.",
                status_code=422,
            ) from exc

    def _guard_dimensions(self, width: int, height: int) -> None:
        pixels = width * height
        if (
            width > self.settings.ocr_max_image_width
            or height > self.settings.ocr_max_image_height
        ):
            raise ApiError(
                code="IMAGE_PARSE_FAILED",
                message="Image dimensions exceed OCR safety limits.",
                status_code=422,
                details={
                    "max_width": self.settings.ocr_max_image_width,
                    "max_height": self.settings.ocr_max_image_height,
                },
            )
        if pixels > self.settings.ocr_max_image_pixels:
            raise ApiError(
                code="IMAGE_PARSE_FAILED",
                message="Image pixel count exceeds OCR safety limits.",
                status_code=422,
                details={"max_pixels": self.settings.ocr_max_image_pixels},
            )

    @staticmethod
    def _parse_confidences(raw_confidences: list[object]) -> list[float]:
        values: list[float] = []
        for raw in raw_confidences:
            try:
                numeric = float(str(raw))
            except (TypeError, ValueError):
                continue
            if numeric < 0:
                continue
            values.append(min(numeric / 100.0, 1.0))
        return values
