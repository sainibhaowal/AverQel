from unittest.mock import MagicMock, patch

import pytest

from app.core.errors import ApiError
from app.ingestion.services.extractors.base import ExtractionRequest
from app.ingestion.services.extractors.docx_extractor import DocxExtractor
from app.ingestion.services.extractors.pptx_extractor import PptxExtractor
from app.ingestion.services.extractors.xlsx_extractor import XlsxExtractor


@patch("app.ingestion.services.extractors.docx_extractor.DocxExtractor._load_document_constructor")
def test_docx_extractor_success(mock_load):
    mock_doc = MagicMock()
    mock_para = MagicMock()
    mock_para.text = "Hello DOCX"
    mock_doc.paragraphs = [mock_para]
    mock_doc.tables = []

    mock_constructor = MagicMock(return_value=mock_doc)
    mock_load.return_value = mock_constructor

    extractor = DocxExtractor(max_text_chars=1000)
    req = ExtractionRequest(
        filename="test.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        payload=b"dummy",
    )

    result = extractor.extract(req)
    assert result.extraction_method == "docx_native"
    assert "Hello DOCX" in result.text
    assert result.coverage_score > 0.0


@patch("app.ingestion.services.extractors.docx_extractor.DocxExtractor._load_document_constructor")
def test_docx_extractor_exceeds_limit(mock_load):
    mock_doc = MagicMock()
    mock_para = MagicMock()
    mock_para.text = "Longtext here"
    mock_doc.paragraphs = [mock_para]
    mock_doc.tables = []

    mock_constructor = MagicMock(return_value=mock_doc)
    mock_load.return_value = mock_constructor

    extractor = DocxExtractor(max_text_chars=5)
    req = ExtractionRequest(
        filename="test.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        payload=b"dummy",
    )

    with pytest.raises(ApiError) as exc:
        extractor.extract(req)
    assert exc.value.code == "DOCUMENT_TEXT_LIMIT_EXCEEDED"


@patch(
    "app.ingestion.services.extractors.pptx_extractor.PptxExtractor._load_presentation_constructor"
)
def test_pptx_extractor_success(mock_load):
    mock_pres = MagicMock()
    mock_slide = MagicMock()
    mock_shape = MagicMock()
    mock_shape.has_text_frame = True
    mock_shape.text = "Hello PPTX"
    mock_shape.has_table = False

    mock_slide.shapes = [mock_shape]
    mock_pres.slides = [mock_slide]

    mock_constructor = MagicMock(return_value=mock_pres)
    mock_load.return_value = mock_constructor

    extractor = PptxExtractor(max_text_chars=1000)
    req = ExtractionRequest(
        filename="test.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        payload=b"dummy",
    )

    result = extractor.extract(req)
    assert result.extraction_method == "pptx_native"
    assert "Hello PPTX" in result.text


@patch("app.ingestion.services.extractors.xlsx_extractor.XlsxExtractor._load_workbook_loader")
def test_xlsx_extractor_success(mock_load):
    mock_wb = MagicMock()
    mock_ws = MagicMock()
    mock_ws.title = "Sheet1"

    # iter_rows(values_only=True) returns literal values, not cell objects
    mock_ws.iter_rows.return_value = [["Hello XLSX", "Cell2"]]
    mock_wb.worksheets = [mock_ws]

    mock_constructor = MagicMock(return_value=mock_wb)
    mock_load.return_value = mock_constructor

    extractor = XlsxExtractor(max_text_chars=1000)
    req = ExtractionRequest(
        filename="test.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        payload=b"dummy",
    )

    result = extractor.extract(req)
    assert result.extraction_method == "xlsx_native"
    assert "C1=Hello XLSX | C2=Cell2" in result.text
