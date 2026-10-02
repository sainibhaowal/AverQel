from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.deepspace.api.library import (
    _MAX_LIBRARY_INLINE_PREVIEW_CHARS,
    LibraryExportRequest,
    LibraryUploadCreate,
    _content_disposition,
    _content_type_for_name,
    _serialize_file,
    _serialize_upload,
)
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.services import library_uploads as uploads_module
from app.deepspace.services.library_uploads import finalize_upload


def test_upload_create_normalizes_filename_and_content_type() -> None:
    payload = LibraryUploadCreate(
        name="research paper.pdf",
        size_bytes=5_000_000,
        content_type="application/pdf; charset=binary",
    )

    assert payload.name == "research paper.pdf"
    assert payload.content_type == "application/pdf"


def test_upload_create_accepts_unicode_names_and_infers_browser_octet_stream_types() -> None:
    payload = LibraryUploadCreate(
        name="研究計画 – résumé.pptx",
        size_bytes=128,
        content_type="application/octet-stream",
    )

    assert payload.name == "研究計画 – résumé.pptx"
    assert _content_type_for_name(payload.name).endswith("presentationml.presentation")


def test_content_disposition_supports_unicode_filenames_without_raw_header_bytes() -> None:
    disposition = _content_disposition(
        disposition="inline",
        filename="NOESIS-Σ - Training Weight.docx",
    )

    disposition.encode("latin-1")
    assert 'filename="NOESIS-_-_Training_Weight.docx"' in disposition
    assert "filename*=UTF-8''NOESIS-%CE%A3%20-%20Training%20Weight.docx" in disposition


def test_library_content_type_mapping_covers_common_data_office_and_media_files() -> None:
    assert _content_type_for_name("table.tsv") == "text/tab-separated-values"
    assert _content_type_for_name("slides.ppt") == "application/vnd.ms-powerpoint"
    assert _content_type_for_name("photo.tiff") == "image/tiff"
    assert _content_type_for_name("recording.flac") == "audio/flac"


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


def _upload(
    *, content_type: str = "text/markdown", expected_size: int = 5
) -> DeepSpaceLibraryUpload:
    return DeepSpaceLibraryUpload(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        filename="notes.md",
        content_type=content_type,
        expected_size=expected_size,
        chunk_size=4,
        total_chunks=2,
        received_chunks=[0, 1],
        bytes_received=expected_size,
        status="processing",
    )


class _Db:
    def __init__(self) -> None:
        self.rows: list[object] = []

    def add(self, row: object) -> None:
        self.rows.append(row)

    def flush(self) -> None:
        return None


def test_finalize_upload_creates_text_file_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Storage:
        def __init__(self, settings: object) -> None:
            self.storage = SimpleNamespace()

        def extract(self, **kwargs: object) -> dict[str, object]:
            return {"text": "extracted"}

    monkeypatch.setattr(uploads_module, "LibraryStorageService", _Storage)
    upload = _upload()
    db = _Db()
    record = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=100),
        upload=upload,
        payload=b"hello",
    )

    assert record.name == "notes.md"
    assert record.content == "hello"
    assert record.is_binary is False
    assert record.extracted_text == "extracted"
    assert len(db.rows) == 2


def test_finalize_upload_rejects_size_mismatch() -> None:
    upload = _upload(expected_size=10)

    with pytest.raises(ApiError, match="does not match"):
        finalize_upload(
            _Db(),
            settings=SimpleNamespace(upload_max_bytes=100),
            upload=upload,
            payload=b"short",
        )


def test_finalize_upload_stores_binary_object_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = SimpleNamespace(bucket="library", object_key="file.bin")

    class _Storage:
        def __init__(self, settings: object) -> None:
            self.storage = SimpleNamespace(delete_object=lambda **kwargs: None)

        def extract(self, **kwargs: object) -> dict[str, object]:
            return {"text": None}

        def store(self, **kwargs: object) -> object:
            return stored

    monkeypatch.setattr(uploads_module, "LibraryStorageService", _Storage)
    upload = _upload(content_type="application/octet-stream")
    db = _Db()
    record = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=100),
        upload=upload,
        payload=b"hello",
    )

    assert record.is_binary is True
    assert record.content == ""
    assert record.storage_bucket == "library"
    assert record.storage_key == "file.bin"


def test_finalize_large_csv_uses_private_object_storage_and_bounded_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = SimpleNamespace(bucket="library", object_key="large.csv")
    extraction_payloads: list[bytes] = []

    class _Storage:
        def __init__(self, settings: object) -> None:
            self.storage = SimpleNamespace(delete_object=lambda **kwargs: None)

        def extract(self, **kwargs: object) -> dict[str, object]:
            extraction_payloads.append(kwargs["payload"])
            return {"text": "column_a,column_b\n1,2"}

        def store(self, **kwargs: object) -> object:
            return stored

    monkeypatch.setattr(uploads_module, "LibraryStorageService", _Storage)
    payload = (b"column_a,column_b\n1,2\n" * 30_000)[:700_000]
    upload = _upload(content_type="text/csv", expected_size=len(payload))
    upload.filename = "large.csv"
    db = _Db()

    record = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=1_000_000),
        upload=upload,
        payload=payload,
    )

    assert record.is_binary is True
    assert record.content == ""
    assert record.storage_bucket == "library"
    assert len(extraction_payloads) == 1
    assert len(extraction_payloads[0]) <= 512 * 1024


def test_library_detail_serialization_bounds_large_text_responses() -> None:
    value = "x" * (_MAX_LIBRARY_INLINE_PREVIEW_CHARS + 20)
    file = SimpleNamespace(
        id=uuid.uuid4(),
        name="large.csv",
        content_type="text/csv",
        source="user",
        size_bytes=len(value),
        created_at=None,
        updated_at=None,
        content=value,
        parent_folder_id=None,
        version=1,
        is_binary=False,
        checksum_sha256=None,
        extracted_text=value,
        conversation_id=uuid.uuid4(),
    )

    result = _serialize_file(file, include_content=True)

    assert result.content_truncated is True
    assert len(result.content or "") == _MAX_LIBRARY_INLINE_PREVIEW_CHARS
    assert len(result.extracted_text or "") == _MAX_LIBRARY_INLINE_PREVIEW_CHARS
