import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.documents.services.pdf_render_service import RenderedPdfPage
from app.ingestion.services.extractors.router import ExtractorRouter
from app.ingestion.services.ocr_service import OcrResult
from tests.support.datasets import ensure_test_datasets

DATASET_ROOT = Path(__file__).parent.parent.parent.parent / "Docs" / "Datasets"


@pytest.fixture
def router(settings: Settings):
    ensure_test_datasets()
    return ExtractorRouter(settings=settings)


def test_clean_documents(router: ExtractorRouter):
    clean_dir = DATASET_ROOT / "clean"
    for file_path in clean_dir.glob("*.*"):
        with open(file_path, "rb") as f:
            payload = f.read()

        content_type = "application/pdf" if file_path.suffix == ".pdf" else "text/plain"
        if file_path.suffix == ".md":
            content_type = "text/markdown"

        result = router.extract(
            filename=file_path.name,
            content_type=content_type,
            payload=payload,
            tenant_id=uuid.uuid4(),
        )
        assert result.coverage_score > 0.0
        assert "ALPHA-CLEAN" in result.text


def test_office_documents(router: ExtractorRouter):
    office_dir = DATASET_ROOT / "office"
    for file_path in office_dir.glob("*.*"):
        with open(file_path, "rb") as f:
            payload = f.read()

        content_types = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }

        result = router.extract(
            filename=file_path.name,
            content_type=content_types[file_path.suffix],
            payload=payload,
            tenant_id=uuid.uuid4(),
        )
        assert result.coverage_score > 0.0
        assert "OFFICE-" in result.text


@patch("app.ingestion.services.ocr_service.OcrService.extract_image_text")
@patch("app.documents.services.pdf_render_service.PdfRenderService.render_pdf_pages")
def test_scanned_documents(mock_render, mock_extract, router: ExtractorRouter):
    mock_extract.return_value = OcrResult(
        text="SCANNED-OCR-001", confidence=0.95, warnings=[], engine="local"
    )
    # Mocking PDF rendering to return 1 page
    mock_render.return_value = [
        RenderedPdfPage(page_number=1, image_bytes=b"fake_image", width=100, height=100)
    ]

    scanned_dir = DATASET_ROOT / "scanned"
    for file_path in scanned_dir.glob("*.*"):
        with open(file_path, "rb") as f:
            payload = f.read()

        content_type = "application/pdf" if file_path.suffix == ".pdf" else "image/png"

        result = router.extract(
            filename=file_path.name,
            content_type=content_type,
            payload=payload,
            tenant_id=uuid.uuid4(),
        )
        assert "SCANNED-OCR" in result.text


@patch("app.ingestion.services.ocr_service.OcrService.extract_image_text")
def test_noisy_images(mock_extract, router: ExtractorRouter):
    mock_extract.return_value = OcrResult(
        text="NOISY-OCR-001", confidence=0.95, warnings=[], engine="local"
    )
    noisy_dir = DATASET_ROOT / "noisy"
    for file_path in noisy_dir.glob("*.*"):
        with open(file_path, "rb") as f:
            payload = f.read()

        result = router.extract(
            filename=file_path.name,
            content_type="image/jpeg",
            payload=payload,
            tenant_id=uuid.uuid4(),
        )
        assert "NOISY-OCR" in result.text
