from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from app.deepspace.workers import library_uploads as upload_workers


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


class _Session:
    def __init__(self, *rows: object) -> None:
        self.rows = list(rows)
        self.row_lock_held = False

    def execute(self, statement: Any, *_args: object, **_kwargs: object) -> _ScalarResult:
        if getattr(statement, "_for_update_arg", None) is not None:
            self.row_lock_held = True
        entities = getattr(statement, "column_descriptions", [])
        entity_name = entities[0]["entity"].__name__ if entities else ""
        if entity_name == "DeepSpaceWorkspaceFile":
            row = next((item for item in self.rows if hasattr(item, "extracted_text")), None)
        elif entity_name == "DeepSpaceLibraryUpload":
            row = next((item for item in self.rows if not hasattr(item, "extracted_text")), None)
        else:
            row = None
        return _ScalarResult(row)

    def commit(self) -> None:
        self.row_lock_held = False

    def rollback(self) -> None:
        self.row_lock_held = False

    def close(self) -> None:
        return None


def test_upload_finalize_does_not_hold_database_lock_during_file_storage(
    monkeypatch: Any,
) -> None:
    tenant_id = uuid.uuid4()
    upload = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        total_chunks=1,
        status="queued",
        metadata_json={},
    )
    session = _Session(upload)
    deleted_objects: list[tuple[str, str]] = []

    class _Storage:
        def __init__(self, _settings: object) -> None:
            pass

        def get_upload_chunk(self, **_kwargs: object) -> bytes:
            return b"image-bytes"

        def delete_upload_chunks(self, **_kwargs: object) -> None:
            return None

        def delete_object(self, *, bucket: str, object_key: str) -> None:
            deleted_objects.append((bucket, object_key))

    monkeypatch.setattr(upload_workers, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(upload_workers, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(upload_workers, "set_db_tenant_context", lambda *_args: None)
    monkeypatch.setattr(upload_workers, "StorageService", _Storage)

    def _slow_finalize(db: _Session, **kwargs: object) -> SimpleNamespace:
        assert not db.row_lock_held, "storage/finalization must run without an upload row lock"
        assert kwargs["extract_content"] is False
        # Simulate the API cancel request winning while storage work is active.
        db.rows[0].status = "cancelled"
        return SimpleNamespace(
            id=uuid.uuid4(),
            storage_bucket="private-library",
            storage_key="tenant/file.png",
            content_type="image/png",
            metadata_json={"extraction_status": {"state": "processing"}},
        )

    monkeypatch.setattr(upload_workers, "finalize_upload", _slow_finalize)

    result = upload_workers.finalize_library_upload.run(
        upload_id=str(upload.id), tenant_id=str(tenant_id)
    )

    assert result == "cancelled"
    assert deleted_objects == [("private-library", "tenant/file.png")]


def test_extraction_worker_updates_file_and_upload_after_file_is_stored(
    monkeypatch: Any,
) -> None:
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    file = SimpleNamespace(
        id=file_id,
        tenant_id=tenant_id,
        metadata_json={"extraction_status": {"state": "processing"}},
        is_binary=True,
        storage_bucket="private-library",
        storage_key="tenant/image.png",
        name="image.png",
        content_type="image/png",
        content=b"",
        extracted_text=None,
    )
    upload = SimpleNamespace(
        file_id=file_id,
        tenant_id=tenant_id,
        metadata_json={"extraction_status": {"state": "processing"}},
    )
    session = _Session(file, upload)

    class _LibraryStorage:
        def __init__(self, _settings: object) -> None:
            self.storage = SimpleNamespace(
                get_bytes=lambda **_kwargs: b"image-bytes",
            )

        def extract(self, **kwargs: object) -> dict[str, object]:
            assert kwargs["payload"] == b"image-bytes"
            return {
                "text": "Invoice total: 42",
                "extraction_method": "image_ocr",
                "ocr_used": True,
            }

    monkeypatch.setattr(upload_workers, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(upload_workers, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(upload_workers, "set_db_tenant_context", lambda *_args: None)
    monkeypatch.setattr(upload_workers, "LibraryStorageService", _LibraryStorage)

    result = upload_workers.extract_library_file.run(file_id=str(file_id), tenant_id=str(tenant_id))

    assert result == "extracted"
    assert file.extracted_text == "Invoice total: 42"
    assert file.metadata_json["extraction_status"]["state"] == "extracted"
    assert "_extraction_attempts" not in file.metadata_json
    assert upload.metadata_json["extraction_status"]["ocr_used"] is True
