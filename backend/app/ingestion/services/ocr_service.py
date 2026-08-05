from __future__ import annotations

import json
import statistics
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from app.core.config import Settings
from app.core.errors import ApiError
from app.ingestion.services.parser_service import sanitize_document_text
from app.system.services.metrics_service import observe_extraction_stage


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
        self._paddle_ocr: Any | None = None
        self._paddle_lock = threading.Lock()

    def extract_image_text(self, payload: bytes, filename: str) -> OcrResult:
        with observe_extraction_stage("ocr"):
            if not self.settings.ocr_enabled:
                raise ApiError(
                    code="OCR_UNAVAILABLE",
                    message="OCR is disabled in service settings.",
                    status_code=503,
                )

            if self.settings.ocr_engine == "paddleocr":
                return self._extract_with_paddleocr(payload=payload, filename=filename)

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
            page_result = self.extract_image_text(image_payload, filename=f"page-{page_number}.png")
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

    def _extract_with_paddleocr(self, *, payload: bytes, filename: str) -> OcrResult:
        image = self._load_image(payload=payload)
        self._guard_dimensions(image.width, image.height)

        try:
            import numpy as np
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="OCR_UNAVAILABLE",
                message="PaddleOCR and its runtime are required for OCR extraction.",
                status_code=503,
            ) from exc

        attempts = max(self.settings.ocr_retry_attempts, 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                ocr = self._get_paddleocr(PaddleOCR)
                # Model initialization/download is a one-time worker startup
                # cost and must not make the first valid upload fail the
                # per-image OCR timeout.
                started = time.perf_counter()
                result = list(ocr.predict(np.asarray(image.convert("RGB"))))
                elapsed = time.perf_counter() - started
                if elapsed > self.settings.ocr_timeout_seconds:
                    raise ApiError(
                        code="OCR_TIMEOUT",
                        message="OCR processing timed out.",
                        status_code=504,
                        details={
                            "timeout_seconds": self.settings.ocr_timeout_seconds,
                            "elapsed_seconds": round(elapsed, 3),
                        },
                    )

                texts, confidence_values = self._extract_paddle_result(result)
                text = sanitize_document_text(" ".join(texts)).strip()
                confidence = statistics.fmean(confidence_values) if confidence_values else 0.0
                warnings: list[str] = []
                if confidence < self.settings.ocr_min_confidence:
                    warnings.append("ocr_low_confidence")
                if not text:
                    warnings.append("ocr_no_text_extracted")
                return OcrResult(
                    text=text,
                    confidence=round(min(max(confidence, 0.0), 1.0), 4),
                    warnings=warnings,
                    engine="paddleocr",
                )
            except ApiError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc

            if attempt < attempts:
                time.sleep(min(0.25 * attempt, 1.0))

        raise ApiError(
            code="OCR_FAILED",
            message="PaddleOCR extraction failed.",
            status_code=422,
            details={"filename": filename},
        ) from last_error

    def _get_paddleocr(self, paddle_ocr_class: Any) -> Any:
        if self._paddle_ocr is not None:
            return self._paddle_ocr

        with self._paddle_lock:
            if self._paddle_ocr is not None:
                return self._paddle_ocr

            language = self._paddle_language(self.settings.ocr_languages)
            options: dict[str, Any] = {
                "device": self.settings.ocr_device,
                # PaddlePaddle's oneDNN path is disabled by default because it
                # is not compatible with some CPU/runtime combinations.
                "enable_mkldnn": self.settings.ocr_enable_mkldnn,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
            }
            if language:
                options["lang"] = language
            # The current PaddleOCR pipeline selects PP-OCRv6 by default.
            self._paddle_ocr = paddle_ocr_class(**options)
            return self._paddle_ocr

    @staticmethod
    def _paddle_language(languages: list[str]) -> str | None:
        if not languages:
            return None
        aliases = {
            "eng": "en",
            "en": "en",
            "deu": "german",
            "de": "german",
            "fra": "french",
            "fr": "french",
            "spa": "es",
            "es": "es",
            "ita": "it",
            "it": "it",
            "por": "pt",
            "pt": "pt",
            "rus": "cyrillic",
            "ru": "cyrillic",
            "hin": "devanagari",
            "hi": "devanagari",
            "ara": "arabic",
            "ar": "arabic",
            "jpn": "japan",
            "ja": "japan",
            "kor": "korean",
            "ko": "korean",
            "chi_sim": "ch",
            "zh": "ch",
        }
        return aliases.get(languages[0].lower(), languages[0].lower())

    @classmethod
    def _extract_paddle_result(cls, results: list[Any]) -> tuple[list[str], list[float]]:
        texts: list[str] = []
        confidence_values: list[float] = []
        for result in results:
            payload = cls._result_mapping(result)
            if not payload:
                continue
            nested = payload.get("res")
            if isinstance(nested, Mapping):
                payload = nested
            raw_texts = payload.get("rec_texts", [])
            raw_scores = payload.get("rec_scores", [])
            result_texts = [
                sanitize_document_text(str(value)).strip()
                for value in raw_texts
                if value is not None
            ]
            texts.extend(value for value in result_texts if value)
            confidence_values.extend(cls._parse_confidences(raw_scores))
        return texts, confidence_values

    @staticmethod
    def _result_mapping(result: Any) -> Mapping[str, Any] | None:
        if isinstance(result, Mapping):
            return result
        for attribute in ("json", "res"):
            value = getattr(result, attribute, None)
            if callable(value):
                value = value()
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    continue
            if isinstance(value, Mapping):
                return value
        try:
            value = dict(result)
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, Mapping) else None

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
        if width > self.settings.ocr_max_image_width or height > self.settings.ocr_max_image_height:
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
            if numeric > 1.0:
                numeric /= 100.0
            values.append(min(numeric, 1.0))
        return values
