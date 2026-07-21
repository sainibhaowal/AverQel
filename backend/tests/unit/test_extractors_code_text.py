from __future__ import annotations

from app.ingestion.services.extractors.base import ExtractionRequest
from app.ingestion.services.extractors.text_extractors import CodeTextExtractor


def test_code_text_extractor_decodes_source() -> None:
    extractor = CodeTextExtractor(max_text_chars=1000)
    result = extractor.extract(
        ExtractionRequest(
            filename="main.py",
            content_type="text/x-python",
            payload=b"def main():\n    return 42\n",
        )
    )
    assert "def main" in result.text
    assert result.extraction_method == "code_text"
    assert result.coverage_score == 1.0


def test_ipynb_extractor_sets_warning() -> None:
    extractor = CodeTextExtractor(max_text_chars=1000)
    result = extractor.extract(
        ExtractionRequest(
            filename="notes.ipynb",
            content_type="application/x-ipynb+json",
            payload=b'{"cells": []}',
        )
    )
    assert "ipynb_flat_text_extraction" in result.warnings
