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
from app.deepspace.services.library_storage import safe_extraction_status
from app.deepspace.services.library_uploads import finalize_upload, unique_library_filename


def test_upload_create_normalizes_filename_and_content_type() -> None:
    payload = LibraryUploadCreate(
        name="research paper.pdf",
        size_bytes=5_000_000,
        content_type="application/pdf; charset=binary",
    )

    assert payload.name == "research paper.pdf"
    assert payload.content_type == "application/pdf"


def test_composer_upload_can_opt_into_unique_names_without_changing_library_default() -> None:
    payload = LibraryUploadCreate(
        name="screenshot.png",
        size_bytes=128,
        content_type="image/png",
        rename_on_conflict=True,
    )
    default_payload = LibraryUploadCreate(name="screenshot.png", size_bytes=128)

    assert payload.rename_on_conflict is True
    assert default_payload.rename_on_conflict is False


def test_unique_library_filename_preserves_extension_and_bounds_long_names() -> None:
    assert unique_library_filename("screenshot.png", {"screenshot.png"}) == "screenshot (2).png"
    assert (
        unique_library_filename("screenshot.png", {"screenshot.png", "screenshot (2).png"})
        == "screenshot (3).png"
    )
    assert unique_library_filename(".env", {".env"}) == ".env (2)"

    long_name = "r" * 255
    unique_name = unique_library_filename(long_name, {long_name})
    assert len(unique_name) == 255
    assert unique_name.endswith(" (2)")


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


def test_safe_extraction_status_reports_ocr_without_storing_extracted_text() -> None:
    status = safe_extraction_status(
        {
            "text": "Scanned invoice total: 42",
            "extraction_method": "pdf_native+pdf_ocr",
            "coverage_score": 0.91,
            "ocr_used": True,
            "vision_used": False,
        }
    )

    assert status == {
        "state": "extracted",
        "text_available": True,
        "extraction_method": "pdf_native+pdf_ocr",
        "ocr_used": True,
        "vision_used": False,
        "coverage_score": 0.91,
        "error_code": None,
    }
    assert "Scanned invoice" not in str(status)


def test_safe_extraction_status_distinguishes_no_text_and_unavailable() -> None:
    no_text = safe_extraction_status({"text": "  ", "ocr_used": True})
    unavailable = safe_extraction_status(
        {"text": None, "extraction_error": "OCR_ENGINE_UNAVAILABLE", "warnings": ["private"]}
    )

    assert no_text["state"] == "no_text"
    assert no_text["ocr_used"] is True
    assert unavailable["state"] == "unavailable"
    assert unavailable["error_code"] == "OCR_ENGINE_UNAVAILABLE"
    assert "private" not in str(unavailable)


def test_safe_extraction_status_exposes_background_processing_state() -> None:
    status = safe_extraction_status({"state": "processing", "text_available": False})

    assert status["state"] == "processing"
    assert status["text_available"] is False


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
            return {
                "text": "extracted",
                "extraction_method": "native_text",
                "ocr_used": False,
                "coverage_score": 0.9,
            }

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
    assert record.metadata_json["extraction_status"]["state"] == "extracted"
    assert record.metadata_json["extraction_status"]["ocr_used"] is False
    assert upload.metadata_json["extraction_status"]["text_available"] is True
    assert _serialize_upload(upload).extraction_status.ocr_used is False
    assert len(db.rows) == 2


def test_identical_payloads_published_under_unique_names_receive_distinct_file_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Storage:
        def __init__(self, _settings: object) -> None:
            self.storage = SimpleNamespace(delete_object=lambda **_kwargs: None)

        def extract(self, **_kwargs: object) -> dict[str, object]:
            return {"text": None}

        def store(self, *, filename: str, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(bucket="private-library", object_key=filename)

    monkeypatch.setattr(uploads_module, "LibraryStorageService", _Storage)
    db = _Db()
    first_upload = _upload(content_type="image/png", expected_size=4)
    first_upload.filename = "screenshot.png"
    second_upload = _upload(content_type="image/png", expected_size=4)
    second_upload.filename = "screenshot (2).png"

    first = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=100),
        upload=first_upload,
        payload=b"same",
    )
    second = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=100),
        upload=second_upload,
        payload=b"same",
    )

    assert first.checksum_sha256 == second.checksum_sha256
    assert first.id != second.id
    assert first.name == "screenshot.png"
    assert second.name == "screenshot (2).png"


def test_finalize_upload_can_publish_file_before_optional_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Storage:
        def __init__(self, settings: object) -> None:
            self.storage = SimpleNamespace()

        def extract(self, **kwargs: object) -> dict[str, object]:
            raise AssertionError("optional extraction must run in its own worker")

    monkeypatch.setattr(uploads_module, "LibraryStorageService", _Storage)
    upload = _upload()
    db = _Db()

    record = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=100),
        upload=upload,
        payload=b"hello",
        extract_content=False,
    )

    assert record.content == "hello"
    assert record.extracted_text is None
    assert record.metadata_json["extraction_status"]["state"] == "processing"
    assert upload.metadata_json["extraction_status"]["state"] == "processing"
    assert _serialize_upload(upload).extraction_status.state == "processing"


def test_finalize_image_upload_persists_upload_time_ocr_for_chat_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = SimpleNamespace(bucket="library", object_key="scan.png")
    extracted_payloads: list[bytes] = []

    class _Storage:
        def __init__(self, settings: object) -> None:
            self.storage = SimpleNamespace(delete_object=lambda **kwargs: None)

        def extract(self, **kwargs: object) -> dict[str, object]:
            extracted_payloads.append(kwargs["payload"])
            return {
                "text": "Invoice total: 42",
                "extraction_method": "image_ocr",
                "coverage_score": 0.95,
                "ocr_used": True,
            }

        def store(self, **kwargs: object) -> object:
            return stored

    monkeypatch.setattr(uploads_module, "LibraryStorageService", _Storage)
    upload = _upload(content_type="image/png")
    upload.filename = "scan.png"
    db = _Db()

    record = finalize_upload(
        db,
        settings=SimpleNamespace(upload_max_bytes=100),
        upload=upload,
        payload=b"image",
    )

    assert extracted_payloads == [b"image"]
    assert record.extracted_text == "Invoice total: 42"
    assert record.metadata_json["extraction_status"]["ocr_used"] is True
    assert _serialize_upload(upload).extraction_status.state == "extracted"


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
