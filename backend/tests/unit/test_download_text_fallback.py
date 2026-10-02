from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from app.core.config import get_settings
from app.ingestion.services.extractors.fallback_file_extractor import extract_fallback_text
from app.ingestion.services.extractors.router import ExtractorRouter


def _zip_payload() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("Index/metadata.xml", "<document><title>Quarterly plan</title></document>")
        archive.writestr("Index/Document.iwa", b"binary SCANNED-FALLBACK-001 metadata")
    return output.getvalue()


def test_iwork_package_gets_bounded_text_fallback() -> None:
    payload = _zip_payload()
    text = extract_fallback_text(filename="plan.pages", payload=payload, max_chars=1000)

    assert "Quarterly plan" in text
    assert "SCANNED-FALLBACK-001" in text


def test_router_accepts_download_only_formats_without_visual_renderer() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    router = ExtractorRouter(settings=settings)

    result = router.extract(
        filename="board.key",
        content_type="application/zip",
        payload=_zip_payload(),
    )

    assert result.extraction_method == "binary_text_fallback"
    assert "download_only_fallback" in result.warnings
    assert "Quarterly plan" in result.text
    assert any(item.extension == ".pages" for item in router.describe_supported_formats())


def test_empty_wps_payload_still_has_download_fallback_metadata() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    router = ExtractorRouter(settings=settings)

    result = router.extract(
        filename="legacy.wps",
        content_type="application/octet-stream",
        payload=b"\x00\x01\x02",
    )

    assert result.text == ""
    assert result.coverage_score == 0.0
    assert "download_only_fallback" in result.warnings
    assert "fallback_no_text_extracted" in result.warnings
