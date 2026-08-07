from __future__ import annotations

import uuid

from app.deepspace.api.library import LibraryExportRequest, LibraryUploadCreate, _serialize_upload
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload


def test_upload_create_normalizes_filename_and_content_type() -> None:
    payload = LibraryUploadCreate(
        name="research paper.pdf",
        size_bytes=5_000_000,
        content_type="application/pdf; charset=binary",
    )

    assert payload.name == "research paper.pdf"
    assert payload.content_type == "application/pdf"


def test_upload_schema_reports_durable_byte_progress() -> None:
    upload = DeepSpaceLibraryUpload(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        filename="notes.md",
        content_type="text/markdown",
        expected_size=10,
        chunk_size=4,
        total_chunks=3,
        received_chunks=[0, 2],
        bytes_received=8,
        status="uploading",
    )

    result = _serialize_upload(upload)

    assert result.received_chunks == [0, 2]
    assert result.bytes_received == 8
    assert result.progress_percent == 80
    assert result.status == "uploading"


def test_export_request_accepts_a_file_selection() -> None:
    selected = uuid.uuid4()
    request = LibraryExportRequest(file_ids=[selected])

    assert request.file_ids == [selected]
