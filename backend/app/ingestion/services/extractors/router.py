from __future__ import annotations

import io
import logging
import mimetypes
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ApiError
from app.documents.services.pdf_render_service import PdfRenderService
from app.ingestion.services.conversion_service import ConversionService
from app.ingestion.services.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.ingestion.services.extractors.docx_extractor import DocxExtractor
from app.ingestion.services.extractors.fallback_file_extractor import extract_fallback_text
from app.ingestion.services.extractors.image_ocr_extractor import ImageOcrExtractor
from app.ingestion.services.extractors.layout_vision_extractor import (
    LayoutVisionExtractor,
)
from app.ingestion.services.extractors.pdf_extractor import PdfExtractor
from app.ingestion.services.extractors.pptx_extractor import PptxExtractor
from app.ingestion.services.extractors.registry import ExtractorRegistry
from app.ingestion.services.extractors.text_extractors import (
    CodeTextExtractor,
    MarkdownExtractor,
    PlainTextExtractor,
)
from app.ingestion.services.extractors.xlsx_extractor import XlsxExtractor
from app.ingestion.services.ocr_service import OcrService
from app.ingestion.services.vision_service import VisionService
from app.system.services.metrics_service import UNSUPPORTED_FORMAT_FALLBACK_TOTAL

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SupportedFormat:
    extension: str
    category: str
    extraction_method: str
    needs_conversion: bool = False


class ExtractorRouter:
    _LEGACY_EXTENSIONS = frozenset({".doc", ".ppt", ".xls"})
    _DOWNLOAD_TEXT_FALLBACK_EXTENSIONS = frozenset(
        {".pages", ".numbers", ".key", ".wps", ".dps", ".et"}
    )

    def __init__(
        self,
        settings: Settings,
        *,
        registry: ExtractorRegistry | None = None,
        conversion_service: ConversionService | None = None,
        vision_extractor: LayoutVisionExtractor | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry or self._build_default_registry(settings)
        self.conversion = conversion_service or ConversionService(settings)
        self.vision_extractor = vision_extractor or LayoutVisionExtractor(settings=settings)

    def extract(
        self,
        *,
        filename: str,
        content_type: str,
        payload: bytes,
        tenant_id: uuid.UUID | None = None,
    ) -> ExtractionResult:
        extension = Path(filename).suffix.lower()
        if extension in self._DOWNLOAD_TEXT_FALLBACK_EXTENSIONS:
            return self._extract_download_text_fallback(
                filename=filename,
                extension=extension,
                payload=payload,
            )

        request = ExtractionRequest(filename=filename, content_type=content_type, payload=payload)
        extractor = self.registry.resolve(request)
        if extractor is not None:
            result = extractor.extract(request)
            result = self._office_image_ocr_fallback(
                filename=filename,
                payload=payload,
                tenant_id=tenant_id,
                result=result,
            )
            if (
                self.settings.vision_enabled
                and result.coverage_score < self.settings.extraction_low_coverage_threshold
                and self._vision_allowed_for_tenant(tenant_id)
                and self.vision_extractor.can_handle(request)
            ):
                return self.vision_extractor.extract_with_primary(request, result)
            return result

        if extension in self._LEGACY_EXTENSIONS:
            converted = self.conversion.convert_legacy(filename=filename, payload=payload)
            converted_result = self.extract(
                filename=converted.filename,
                content_type=converted.content_type,
                payload=converted.payload,
                tenant_id=tenant_id,
            )
            converted_result.warnings = [
                *converted.warnings,
                *converted_result.warnings,
            ]
            return converted_result

        if self.conversion.can_convert_to_pdf(filename):
            converted_pdf = self.conversion.convert_to_pdf(filename=filename, payload=payload)
            converted_result = self.extract(
                filename=f"{Path(filename).stem}.pdf",
                content_type="application/pdf",
                payload=converted_pdf,
                tenant_id=tenant_id,
            )
            converted_result.warnings = [
                "libreoffice_preview_conversion_applied",
                *converted_result.warnings,
            ]
            return converted_result

        raise ApiError(
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported document type for parsing.",
            status_code=400,
            details={
                "supported_extensions": self.settings.upload_allowed_extensions,
                "supported_mime_types": self.settings.upload_allowed_mime_types,
            },
        )

    def _extract_download_text_fallback(
        self,
        *,
        filename: str,
        extension: str,
        payload: bytes,
    ) -> ExtractionResult:
        UNSUPPORTED_FORMAT_FALLBACK_TOTAL.labels(extension=extension).inc()
        fallback_text = extract_fallback_text(
            filename=filename,
            payload=payload,
            max_chars=self.settings.parser_max_text_chars,
        )
        warnings = [
            "unsupported_visual_format",
            "download_only_fallback",
        ]
        if not fallback_text:
            warnings.append("fallback_no_text_extracted")
        return ExtractionResult(
            text=fallback_text,
            page_count=None,
            extraction_method="binary_text_fallback",
            coverage_score=0.25 if fallback_text else 0.0,
            warnings=warnings,
        )

    def _office_image_ocr_fallback(
        self,
        *,
        filename: str,
        payload: bytes,
        tenant_id: uuid.UUID | None,
        result: ExtractionResult,
    ) -> ExtractionResult:
        """Supplement native OOXML text with OCR from embedded scanned images."""
        extension = Path(filename).suffix.lower()
        has_embedded_images = self._office_contains_embedded_images(payload, extension)
        native_text = result.text.strip()
        if has_embedded_images and self.settings.ocr_enabled:
            result = self._office_embedded_image_ocr(
                payload=payload,
                extension=extension,
                result=result,
            )
            if (
                result.text.strip() != native_text
                or "office_embedded_image_ocr_used" in result.warnings
            ):
                return result
        can_convert_to_pdf = getattr(self.conversion, "can_convert_to_pdf", None)
        if (
            extension not in {".docx", ".pptx", ".xlsx"}
            or (len(result.text.strip()) >= 120 and not has_embedded_images)
            or not callable(can_convert_to_pdf)
            or not can_convert_to_pdf(filename)
            or not (shutil.which("soffice") or shutil.which("libreoffice"))
        ):
            return result
        try:
            converted_pdf = self.conversion.convert_to_pdf(filename=filename, payload=payload)
            visual = self.extract(
                filename=f"{Path(filename).stem}.pdf",
                content_type="application/pdf",
                payload=converted_pdf,
                tenant_id=tenant_id,
            )
        except ApiError:
            # A failed optional preview/OCR pass must not discard text already
            # recovered by the native Office parser.
            return result
        native_text = result.text.strip()
        visual_text = visual.text.strip()
        if not visual_text:
            return result
        native_lines = {
            line.strip().casefold() for line in native_text.splitlines() if line.strip()
        }
        additional_lines = [
            line.strip()
            for line in visual_text.splitlines()
            if line.strip() and line.strip().casefold() not in native_lines
        ]
        if native_text and native_text in visual_text:
            merged_text = visual_text
        elif additional_lines:
            merged_text = "\n\n".join(
                part for part in (native_text, "\n".join(additional_lines)) if part
            )
        elif len(visual_text) > len(native_text) and not native_text:
            merged_text = visual_text
        else:
            merged_text = native_text
        if not merged_text:
            return result
        max_chars = max(1, int(self.settings.parser_max_text_chars))
        merged_text = merged_text[:max_chars]
        return ExtractionResult(
            text=merged_text,
            page_count=visual.page_count or result.page_count,
            extraction_method=(
                f"{result.extraction_method}+{visual.extraction_method}"
                if additional_lines or native_text in visual_text
                else result.extraction_method
            ),
            coverage_score=max(result.coverage_score, visual.coverage_score),
            ocr_used=result.ocr_used or visual.ocr_used,
            vision_used=result.vision_used or visual.vision_used,
            warnings=self._dedupe(
                ["office_pdf_ocr_fallback_used", *result.warnings, *visual.warnings]
            ),
            layout_blocks=[*result.layout_blocks, *visual.layout_blocks],
        )

    @staticmethod
    def _office_contains_embedded_images(payload: bytes, extension: str) -> bool:
        media_directory = {
            ".docx": "word/media/",
            ".pptx": "ppt/media/",
            ".xlsx": "xl/media/",
        }.get(extension)
        if not media_directory:
            return False
        image_suffixes = {
            ".bmp",
            ".emf",
            ".gif",
            ".jpeg",
            ".jpg",
            ".png",
            ".svg",
            ".tif",
            ".tiff",
            ".webp",
            ".wmf",
        }
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                infos = archive.infolist()
                if len(infos) > 10_000:
                    return False
                return any(
                    info.filename.casefold().startswith(media_directory)
                    and Path(info.filename).suffix.casefold() in image_suffixes
                    and not info.is_dir()
                    for info in infos
                )
        except (OSError, zipfile.BadZipFile):
            return False

    def _office_embedded_image_ocr(
        self,
        *,
        payload: bytes,
        extension: str,
        result: ExtractionResult,
    ) -> ExtractionResult:
        """OCR a bounded set of raster images embedded in an Office archive."""
        media_directory = {
            ".docx": "word/media/",
            ".pptx": "ppt/media/",
            ".xlsx": "xl/media/",
        }.get(extension)
        if not media_directory:
            return result
        image_suffixes = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
        max_image_bytes = 10 * 1024 * 1024
        max_total_image_bytes = 25 * 1024 * 1024
        max_images = 10
        image_requests: list[ExtractionRequest] = []
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                infos = archive.infolist()
                if len(infos) > 10_000:
                    return result
                total_image_bytes = 0
                for info in infos:
                    suffix = Path(info.filename).suffix.casefold()
                    if (
                        not info.filename.casefold().startswith(media_directory)
                        or suffix not in image_suffixes
                        or info.is_dir()
                        or info.file_size <= 0
                        or info.file_size > max_image_bytes
                        or total_image_bytes + info.file_size > max_total_image_bytes
                    ):
                        continue
                    content_type = mimetypes.guess_type(info.filename)[0]
                    if not content_type or not content_type.startswith("image/"):
                        continue
                    with archive.open(info) as stream:
                        image_payload = stream.read(max_image_bytes + 1)
                    if len(image_payload) != info.file_size or len(image_payload) > max_image_bytes:
                        continue
                    image_requests.append(
                        ExtractionRequest(
                            filename=Path(info.filename).name,
                            content_type=content_type,
                            payload=image_payload,
                        )
                    )
                    total_image_bytes += len(image_payload)
                    if len(image_requests) >= max_images:
                        break
        except (OSError, zipfile.BadZipFile):
            return result
        if not image_requests:
            return result

        extracted_text: list[str] = []
        warnings = list(result.warnings)
        image_extraction_method: str | None = None
        coverage_score = result.coverage_score
        for request in image_requests:
            extractor = self.registry.resolve(request)
            if extractor is None:
                continue
            try:
                image_result = extractor.extract(request)
            except Exception:  # noqa: BLE001
                logger.warning("OCR failed for an embedded Office image")
                warnings.append("office_embedded_image_ocr_failed")
                continue
            image_extraction_method = image_result.extraction_method
            coverage_score = max(coverage_score, image_result.coverage_score)
            warnings.extend(image_result.warnings)
            image_text = image_result.text.strip()
            if image_text:
                extracted_text.append(image_text)
        if not extracted_text:
            if image_extraction_method:
                warnings.append("office_embedded_image_ocr_no_text")
            return ExtractionResult(
                text=result.text,
                page_count=result.page_count,
                extraction_method=(
                    f"{result.extraction_method}+{image_extraction_method}"
                    if image_extraction_method and result.extraction_method
                    else image_extraction_method or result.extraction_method
                ),
                coverage_score=coverage_score,
                ocr_used=result.ocr_used or bool(image_extraction_method),
                vision_used=result.vision_used,
                warnings=self._dedupe(warnings),
                layout_blocks=list(result.layout_blocks),
            )

        existing_lines = {
            line.strip().casefold() for line in result.text.splitlines() if line.strip()
        }
        new_lines = [
            line.strip()
            for text in extracted_text
            for line in text.splitlines()
            if line.strip() and line.strip().casefold() not in existing_lines
        ]
        if not new_lines:
            return ExtractionResult(
                text=result.text,
                page_count=result.page_count,
                extraction_method=(
                    f"{result.extraction_method}+{image_extraction_method}"
                    if result.extraction_method and image_extraction_method
                    else image_extraction_method or result.extraction_method
                ),
                coverage_score=coverage_score,
                ocr_used=True,
                vision_used=result.vision_used,
                warnings=self._dedupe(["office_embedded_image_ocr_used", *warnings]),
                layout_blocks=list(result.layout_blocks),
            )
        max_chars = max(1, int(self.settings.parser_max_text_chars))
        combined_text = "\n\n".join(
            part for part in (result.text.strip(), "\n".join(new_lines)) if part
        )[:max_chars]
        return ExtractionResult(
            text=combined_text,
            page_count=result.page_count,
            extraction_method=(
                f"{result.extraction_method}+{image_extraction_method}"
                if result.extraction_method and image_extraction_method
                else image_extraction_method or result.extraction_method
            ),
            coverage_score=coverage_score,
            ocr_used=True,
            vision_used=result.vision_used,
            warnings=self._dedupe(["office_embedded_image_ocr_used", *warnings]),
            layout_blocks=list(result.layout_blocks),
        )

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))

    def describe_supported_formats(self) -> list[SupportedFormat]:
        formats: list[SupportedFormat] = []
        for extractor in self.registry.extractors:
            for extension in sorted(extractor.supported_extensions):
                formats.append(
                    SupportedFormat(
                        extension=extension,
                        category=self._category_for_extractor(extractor),
                        extraction_method=extractor.extraction_method,
                    )
                )
        formats.extend(
            SupportedFormat(
                extension=extension,
                category="libreoffice-visual",
                extraction_method="libreoffice_headless",
                needs_conversion=True,
            )
            for extension in sorted(self.conversion.renderable_extensions)
            if extension not in {item.extension for item in formats}
        )
        formats.extend(
            SupportedFormat(
                extension=extension,
                category="download-text-fallback",
                extraction_method="binary_text_fallback",
                needs_conversion=False,
            )
            for extension in sorted(self._DOWNLOAD_TEXT_FALLBACK_EXTENSIONS)
            if extension not in {item.extension for item in formats}
        )
        return formats

    def _vision_allowed_for_tenant(self, tenant_id: uuid.UUID | None) -> bool:
        allowlist = self.settings.vision_tenant_allowlist
        if not allowlist:
            return True
        if tenant_id is None:
            return False
        return str(tenant_id) in set(allowlist)

    def _build_default_registry(self, settings: Settings) -> ExtractorRegistry:
        ocr_service = OcrService(settings)
        render_service = PdfRenderService(settings)
        vision_service = VisionService(settings=settings, ocr_service=ocr_service)
        vision_extractor = LayoutVisionExtractor(
            settings=settings,
            vision_service=vision_service,
            pdf_render_service=render_service,
            ocr_service=ocr_service,
        )
        self.vision_extractor = vision_extractor
        registry = ExtractorRegistry()
        registry.register(
            PdfExtractor(
                max_pdf_pages=settings.parser_max_pdf_pages,
                max_text_chars=settings.parser_max_text_chars,
                settings=settings,
                ocr_service=ocr_service,
                pdf_render_service=render_service,
                vision_extractor=vision_extractor,
            )
        )
        registry.register(PlainTextExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(MarkdownExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(ImageOcrExtractor(settings=settings, ocr_service=ocr_service))
        registry.register(DocxExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(PptxExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(XlsxExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(CodeTextExtractor(max_text_chars=settings.parser_max_text_chars))
        return registry

    @staticmethod
    def _category_for_extractor(extractor: BaseExtractor) -> str:
        method = extractor.extraction_method
        if method.startswith("pdf"):
            return "pdf"
        if method.startswith("docx"):
            return "office-document"
        if method.startswith("pptx"):
            return "office-presentation"
        if method.startswith("xlsx"):
            return "office-spreadsheet"
        if method.startswith("image"):
            return "image"
        if method.startswith("layout_vision"):
            return "vision"
        if method.startswith("code"):
            return "code"
        if method.startswith("markdown") or method.startswith("plain"):
            return "text"
        return "other"
