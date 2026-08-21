from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.errors import ApiError
from app.deepspace.api.library import (
    LibraryExportRequest,
    LibraryUploadCreate,
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
