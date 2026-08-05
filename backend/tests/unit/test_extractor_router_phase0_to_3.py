from dataclasses import dataclass
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
