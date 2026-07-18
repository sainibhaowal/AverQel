from __future__ import annotations

import pytest

from app.services.ingestion.chunking_service import ChunkingService


def test_chunking_generates_expected_windows() -> None:
    service = ChunkingService()
    text = "a" * 1200
    chunks = service.chunk(text, chunk_size=500, overlap=100, min_length=10)
    assert len(chunks) >= 2
    assert chunks[0].char_start == 0
    assert chunks[1].char_start < chunks[1].char_end


def test_chunking_rejects_invalid_overlap() -> None:
    service = ChunkingService()
    with pytest.raises(ValueError):
        service.chunk("hello world", chunk_size=100, overlap=100, min_length=1)


def test_chunking_adds_mode_and_source_metadata() -> None:
    service = ChunkingService()
    chunks = service.chunk(
        "alpha beta gamma delta",
        chunk_size=8,
        overlap=2,
        min_length=2,
        mode="code",
        source_metadata={"extraction_method": "code_text"},
    )
    assert chunks
    assert chunks[0].metadata["mode"] == "code"
    assert chunks[0].metadata["extraction_method"] == "code_text"


def test_chunking_structured_blocks_preserve_page_anchor() -> None:
    service = ChunkingService()
    chunks = service.chunk_structured(
        blocks=[
            {
                "block_type": "table",
                "text": "col1 | col2\\n1 | 2",
                "page_number": 3,
                "coordinates": {"x": 12.3, "y": 4.5},
            }
        ],
        chunk_size=80,
        overlap=0,
        min_length=1,
    )
    assert len(chunks) == 1
    assert chunks[0].metadata["mode"] == "table"
    assert chunks[0].metadata["page_number"] == 3
    assert "coord_x" in chunks[0].metadata
