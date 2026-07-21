from __future__ import annotations

import uuid
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


@dataclass(slots=True)
class SupportedFormat:
    extension: str
    category: str
    extraction_method: str
    needs_conversion: bool = False


class ExtractorRouter:
    _LEGACY_EXTENSIONS = frozenset({".doc", ".ppt", ".xls"})

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
        self.vision_extractor = vision_extractor or LayoutVisionExtractor(
            settings=settings
        )

    def extract(
        self,
        *,
        filename: str,
        content_type: str,
        payload: bytes,
        tenant_id: uuid.UUID | None = None,
    ) -> ExtractionResult:
        request = ExtractionRequest(
            filename=filename, content_type=content_type, payload=payload
        )
        extractor = self.registry.resolve(request)
        if extractor is not None:
            result = extractor.extract(request)
            if (
                self.settings.vision_enabled
                and result.coverage_score
                < self.settings.extraction_low_coverage_threshold
                and self._vision_allowed_for_tenant(tenant_id)
                and self.vision_extractor.can_handle(request)
            ):
                return self.vision_extractor.extract_with_primary(request, result)
            return result

        extension = Path(filename).suffix.lower()
        if extension in self._LEGACY_EXTENSIONS:
            converted = self.conversion.convert_legacy(
                filename=filename, payload=payload
            )
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

        raise ApiError(
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported document type for parsing.",
            status_code=400,
            details={
                "supported_extensions": self.settings.upload_allowed_extensions,
                "supported_mime_types": self.settings.upload_allowed_mime_types,
            },
        )

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
                category="legacy-office",
                extraction_method="libreoffice_headless",
                needs_conversion=True,
            )
            for extension in sorted(self._LEGACY_EXTENSIONS)
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
        registry.register(
            PlainTextExtractor(max_text_chars=settings.parser_max_text_chars)
        )
        registry.register(
            MarkdownExtractor(max_text_chars=settings.parser_max_text_chars)
        )
        registry.register(ImageOcrExtractor(settings=settings, ocr_service=ocr_service))
        registry.register(DocxExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(PptxExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(XlsxExtractor(max_text_chars=settings.parser_max_text_chars))
        registry.register(
            CodeTextExtractor(max_text_chars=settings.parser_max_text_chars)
        )
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
