import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import cast

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.ingestion.services.conversion_service import (
    ConversionService,
    ConvertedArtifact,
)
from app.ingestion.services.extractors.base import (
    BaseExtractor,
    ExtractionRequest,
    ExtractionResult,
)
from app.ingestion.services.extractors.registry import ExtractorRegistry
from app.ingestion.services.extractors.router import ExtractorRouter


class _FakeExtractor(BaseExtractor):
    extraction_method = "fake_native"
    supported_extensions = frozenset({".fake"})
    supported_mime_types = frozenset({"application/x-fake"})

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult(
            text=request.payload.decode("utf-8"),
            page_count=None,
            extraction_method=self.extraction_method,
            coverage_score=1.0,
            warnings=[],
        )


class _ConvertedDocxExtractor(BaseExtractor):
    extraction_method = "docx_native"
    supported_extensions = frozenset({".docx"})
    supported_mime_types = frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        return ExtractionResult(
            text="converted docx text",
            page_count=None,
            extraction_method=self.extraction_method,
            coverage_score=0.91,
            warnings=["docx_partial_table_layout"],
        )


class _OfficeImageExtractor(BaseExtractor):
    extraction_method = "docx_native"
    supported_extensions = frozenset({".docx"})
    supported_mime_types = frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    )

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        _ = request
        return ExtractionResult(
            text="Native Office text. " * 12,
            page_count=None,
            extraction_method=self.extraction_method,
            coverage_score=0.9,
        )


class _ScannedPdfExtractor(BaseExtractor):
    extraction_method = "pdf_native+pdf_ocr"
    supported_extensions = frozenset({".pdf"})
    supported_mime_types = frozenset({"application/pdf"})

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        _ = request
        return ExtractionResult(
            text="Scanned label recovered by OCR",
            page_count=1,
            extraction_method=self.extraction_method,
            coverage_score=0.9,
            ocr_used=True,
        )


class _EmbeddedImageOcrExtractor(BaseExtractor):
    extraction_method = "image_ocr"
    supported_extensions = frozenset({".png"})
    supported_mime_types = frozenset({"image/png"})

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        _ = request
        return ExtractionResult(
            text="Scanned table total: 125",
            page_count=1,
            extraction_method=self.extraction_method,
            coverage_score=0.95,
            ocr_used=True,
        )


@dataclass(slots=True)
class _FakeConversionService:
    called: bool = False

    def convert_legacy(self, *, filename: str, payload: bytes) -> ConvertedArtifact:
        self.called = True
        _ = payload
        assert filename.endswith(".doc")
        return ConvertedArtifact(
            filename="converted.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            payload=b"docx",
            warnings=["legacy_conversion_applied"],
        )


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


def test_registry_resolves_first_matching_extractor() -> None:
    registry = ExtractorRegistry()
    extractor = _FakeExtractor()
    registry.register(extractor)

    resolved = registry.resolve(
        ExtractionRequest(filename="a.fake", content_type="application/octet-stream", payload=b"x")
    )
    assert resolved is extractor


def test_router_extracts_native_format(settings) -> None:
    registry = ExtractorRegistry()
    registry.register(_FakeExtractor())
    router = ExtractorRouter(settings=settings, registry=registry)

    result = router.extract(filename="a.fake", content_type="application/x-fake", payload=b"hello")
    assert result.text == "hello"
    assert result.extraction_method == "fake_native"
    assert result.coverage_score == 1.0


def test_router_converts_legacy_and_merges_warnings(settings) -> None:
    registry = ExtractorRegistry()
    registry.register(_ConvertedDocxExtractor())
    conversion = _FakeConversionService()
    router = ExtractorRouter(
        settings=settings,
        registry=registry,
        conversion_service=cast(ConversionService, conversion),
    )

    result = router.extract(
        filename="legacy.doc", content_type="application/msword", payload=b"legacy"
    )
    assert conversion.called is True
    assert result.text == "converted docx text"
    assert result.warnings[0] == "legacy_conversion_applied"
    assert "docx_partial_table_layout" in result.warnings


def test_router_ocr_fallback_scans_images_in_mixed_text_office_documents(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _OfficeConversion:
        called = False

        def can_convert_to_pdf(self, filename: str) -> bool:
            return filename.endswith(".docx")

        def convert_to_pdf(self, *, filename: str, payload: bytes) -> bytes:
            _ = (filename, payload)
            self.called = True
            return b"converted pdf"

    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("word/media/scanned-page.png", b"image placeholder")
    registry = ExtractorRegistry()
    registry.register(_OfficeImageExtractor())
    registry.register(_ScannedPdfExtractor())
    conversion = _OfficeConversion()
    monkeypatch.setattr(
        "app.ingestion.services.extractors.router.shutil.which",
        lambda _name: "/usr/bin/soffice",
    )
    settings.vision_enabled = False
    router = ExtractorRouter(
        settings=settings,
        registry=registry,
        conversion_service=cast(ConversionService, conversion),
    )

    result = router.extract(
        filename="mixed.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        payload=archive_buffer.getvalue(),
    )

    assert conversion.called is True
    assert "Native Office text." in result.text
    assert "Scanned label recovered by OCR" in result.text
    assert result.ocr_used is True
    assert "office_pdf_ocr_fallback_used" in result.warnings


def test_router_ocr_extracts_embedded_raster_image_when_office_text_is_substantial(
    settings,
) -> None:
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("word/media/scanned-page.png", b"image placeholder")
    registry = ExtractorRegistry()
    registry.register(_OfficeImageExtractor())
    registry.register(_EmbeddedImageOcrExtractor())
    router = ExtractorRouter(settings=settings, registry=registry)

    result = router.extract(
        filename="mixed.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        payload=archive_buffer.getvalue(),
    )

    assert "Native Office text." in result.text
    assert "Scanned table total: 125" in result.text
    assert result.ocr_used is True
    assert result.extraction_method == "docx_native+image_ocr"
    assert "office_embedded_image_ocr_used" in result.warnings


def test_router_rejects_unknown_type(settings) -> None:
    router = ExtractorRouter(settings=settings, registry=ExtractorRegistry())
    with pytest.raises(ApiError) as exc_info:
        router.extract(
            filename="unknown.bin",
            content_type="application/octet-stream",
            payload=b"x",
        )
    assert exc_info.value.code == "UNSUPPORTED_DOCUMENT_TYPE"


def test_conversion_service_requires_libo_binary(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ConversionService(settings)
    monkeypatch.setattr(
        "app.ingestion.services.conversion_service.shutil.which", lambda _name: None
    )

    with pytest.raises(ApiError) as exc_info:
        service.convert_legacy(filename="legacy.doc", payload=b"x")
    assert exc_info.value.code == "LEGACY_CONVERSION_UNAVAILABLE"
