from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.ingestion.services.ingestion_service import (
    IngestionService,
    RetryableIngestionError,
    make_storage_key,
)
from app.system.services.storage_service import StorageServiceError


class _DB:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


@dataclass
class _Part:
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    metadata: dict


class _Jobs:
    def __init__(self, job, *, max_attempts: int = 3) -> None:
        self.job = job
        self.max_attempts = max_attempts
        self.set_calls: list[dict] = []
        self.latest_job = job

    def get_by_id(self, *, tenant_id, job_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, job_id)
        return self.job

    def get_by_document_id(self, *, tenant_id, document_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document_id)
        return self.latest_job

    def set_status(self, **kwargs):  # type: ignore[no-untyped-def]
        self.set_calls.append(kwargs)

    def increment_attempt(self, *, tenant_id, job):  # type: ignore[no-untyped-def]
        _ = tenant_id
        job.attempt_count += 1


class _Docs:
    def __init__(self, doc) -> None:  # type: ignore[no-untyped-def]
        self.doc = doc
        self.status_calls: list[str] = []
        self.progress_calls: list[tuple[int, str | None]] = []

    def get_by_id(self, *, tenant_id, document_id):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document_id)
        return self.doc

    def set_status(self, *, tenant_id, document, status):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document)
        self.status_calls.append(status)

    def set_extraction_metadata(self, *, tenant_id, document, extraction):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document, extraction)
        return None

    def set_processing_progress(self, *, tenant_id, document_id, progress, status=None):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document_id)
        self.progress_calls.append((progress, status))
        if self.doc is not None:
            self.doc.processing_progress = progress
            if status is not None:
                self.doc.status = status


class _Chunks:
    def replace_document_chunks(self, *, tenant_id, document_id, chunks):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document_id)
        return chunks

    def replace_chunk_embeddings(self, *, tenant_id, document_id, embeddings):  # type: ignore[no-untyped-def]
        _ = (tenant_id, document_id, embeddings)
        return None


def _service(settings):  # type: ignore[no-untyped-def]
    service = object.__new__(IngestionService)
    service.db = _DB()
    service.settings = settings
    service.jobs = _Jobs(None)
    service.documents = _Docs(None)
    service.chunks = _Chunks()
    service.storage = SimpleNamespace(get_bytes=lambda **kwargs: b"data")
    service.parser = SimpleNamespace(
        parse_bytes=lambda **kwargs: SimpleNamespace(text="content")
    )
    service.chunking = SimpleNamespace(
        chunk=lambda *_args, **_kwargs: [_Part(0, "chunk text", 0, 10, {})]
    )
    service.embedding = SimpleNamespace(
        embed_many=lambda texts: [[0.1] * settings.embedding_dimension for _ in texts]
    )
    service._publish_update = lambda *args, **kwargs: None
    return service


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


def test_process_ingestion_job_not_found_returns(
    settings, caplog: pytest.LogCaptureFixture
) -> None:
    service = _service(settings)
    service.jobs = _Jobs(None)
    service.process_ingestion_job(tenant_id=uuid4(), job_id=uuid4())
    assert "ingestion job not found" in caplog.text


def test_process_ingestion_job_missing_document_dead_letters(settings) -> None:
    job = SimpleNamespace(
        id=uuid4(), document_id=uuid4(), attempt_count=0, max_attempts=3
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(None)

    service.process_ingestion_job(tenant_id=uuid4(), job_id=uuid4())
    assert any(call.get("status") == "dead_lettered" for call in service.jobs.set_calls)


def test_process_ingestion_job_skips_superseded_job(settings) -> None:
    tenant_id = uuid4()
    old_job = SimpleNamespace(
        id=uuid4(),
        document_id=uuid4(),
        attempt_count=0,
        max_attempts=3,
        status="queued",
    )
    latest_job = SimpleNamespace(
        id=uuid4(),
        document_id=old_job.document_id,
        attempt_count=0,
        max_attempts=3,
        status="queued",
    )
    doc = SimpleNamespace(
        id=old_job.document_id,
        status="queued",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(old_job)
    service.jobs.latest_job = latest_job
    service.documents = _Docs(doc)

    service.process_ingestion_job(tenant_id=tenant_id, job_id=old_job.id)
    assert any(
        call.get("error_code") == "SUPERSEDED_JOB" for call in service.jobs.set_calls
    )


def test_process_ingestion_job_marks_already_indexed_job_complete(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        document_id=uuid4(),
        attempt_count=0,
        max_attempts=3,
        status="queued",
    )
    doc = SimpleNamespace(
        id=job.document_id,
        status="indexed",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)

    service.process_ingestion_job(tenant_id=tenant_id, job_id=job.id)
    assert any(call.get("status") == "indexed" for call in service.jobs.set_calls)


def test_process_ingestion_job_persists_stage_progress(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(),
        document_id=uuid4(),
        attempt_count=0,
        max_attempts=3,
        status="queued",
    )
    doc = SimpleNamespace(
        id=job.document_id,
        tenant_id=tenant_id,
        status="queued",
        processing_progress=0,
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
        information_yield=None,
        extraction_method=None,
        extraction_coverage_score=None,
        extraction_ocr_used=False,
        extraction_vision_used=False,
        extraction_warnings=[],
        language=None,
        quarantined=False,
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)
    service._extract_document_text = lambda **kwargs: SimpleNamespace(  # type: ignore[no-untyped-def]
        text="content",
        warnings=[],
        extraction_method="native",
        coverage_score=1.0,
        ocr_used=False,
        vision_used=False,
        layout_blocks=[],
    )
    service.chunking = SimpleNamespace(
        chunk=lambda *_args, **_kwargs: [
            _Part(0, "chunk one", 0, 9, {}),
            _Part(1, "chunk two", 10, 19, {}),
        ]
    )
    service.embedding = SimpleNamespace(
        embed_many_with_metadata=lambda texts, tenant_id=None: SimpleNamespace(  # type: ignore[no-untyped-def]
            vectors=[[0.1] * settings.embedding_dimension for _ in texts],
            metadata=SimpleNamespace(
                provider="sentence-transformers", model="BAAI/bge-small-en-v1.5"
            ),
        )
    )

    service.process_ingestion_job(tenant_id=tenant_id, job_id=uuid4())

    recorded_progress = [
        progress for progress, _status in service.documents.progress_calls
    ]
    assert 5 in recorded_progress
    assert 10 in recorded_progress
    assert 25 in recorded_progress
    assert 60 in recorded_progress
    assert 100 in recorded_progress


def test_process_ingestion_job_empty_parse_marks_failed(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(), document_id=uuid4(), attempt_count=0, max_attempts=3
    )
    doc = SimpleNamespace(
        id=job.document_id,
        status="queued",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)
    service.parser = SimpleNamespace(
        parse_bytes=lambda **kwargs: SimpleNamespace(text="   ")
    )

    service.process_ingestion_job(tenant_id=tenant_id, job_id=uuid4())
    assert "failed" in service.documents.status_calls


def test_process_ingestion_job_no_parts_marks_failed(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(), document_id=uuid4(), attempt_count=0, max_attempts=3
    )
    doc = SimpleNamespace(
        id=job.document_id,
        status="queued",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)
    service.chunking = SimpleNamespace(chunk=lambda *_a, **_kw: [])

    service.process_ingestion_job(tenant_id=tenant_id, job_id=uuid4())
    assert "failed" in service.documents.status_calls


def test_process_ingestion_job_all_sanitized_out_marks_failed(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(), document_id=uuid4(), attempt_count=0, max_attempts=3
    )
    doc = SimpleNamespace(
        id=job.document_id,
        status="queued",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)
    service.chunking = SimpleNamespace(
        chunk=lambda *_args, **_kwargs: [_Part(0, "\x00\x00", 0, 2, {})]
    )

    service.process_ingestion_job(tenant_id=tenant_id, job_id=uuid4())
    assert "failed" in service.documents.status_calls


def test_process_ingestion_job_storage_error_path(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(), document_id=uuid4(), attempt_count=0, max_attempts=1
    )
    doc = SimpleNamespace(
        id=job.document_id,
        status="queued",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)

    def _raise_storage(**kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        raise StorageServiceError(
            code="STORAGE_UNAVAILABLE", message="down", retryable=False
        )

    service.storage = SimpleNamespace(get_bytes=_raise_storage)
    service.process_ingestion_job(tenant_id=tenant_id, job_id=uuid4())
    assert "failed" in service.documents.status_calls


def test_process_ingestion_job_unhandled_exception_triggers_retryable(settings) -> None:
    tenant_id = uuid4()
    job = SimpleNamespace(
        id=uuid4(), document_id=uuid4(), attempt_count=0, max_attempts=3
    )
    doc = SimpleNamespace(
        id=job.document_id,
        status="queued",
        filename="x.pdf",
        content_type="application/pdf",
        storage_bucket="b",
        storage_object_key="k",
    )
    service = _service(settings)
    service.jobs = _Jobs(job)
    service.documents = _Docs(doc)
    service.parser = SimpleNamespace(
        parse_bytes=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with pytest.raises(RetryableIngestionError):
        service.process_ingestion_job(tenant_id=tenant_id, job_id=uuid4())


def test_validate_upload_branches_and_make_storage_key(settings) -> None:
    service = _service(settings)

    with pytest.raises(ApiError):
        service._validate_upload(
            filename="   ", content_type="application/pdf", payload=b"x"
        )

    with pytest.raises(ApiError):
        service._validate_upload(
            filename="x.pdf", content_type="application/zip", payload=b"x"
        )

    with pytest.raises(ApiError):
        service._validate_upload(
            filename="x.pdf",
            content_type="application/pdf",
            payload=b"x" * (settings.upload_max_bytes + 1),
        )

    key = make_storage_key(
        tenant_id=uuid4(),
        document_id=uuid4(),
        filename="../../unsafe/name.pdf",
    )
    assert "unsafe/name.pdf" not in key
    assert key.endswith("/name.pdf")


@pytest.mark.parametrize(
    ("filename", "content_type", "sniffed_mime"),
    [
        (
            "report.docx",
            "application/octet-stream",
            "application/zip",
        ),
        (
            "legacy.doc",
            "application/octet-stream",
            "application/x-ole-storage",
        ),
        (
            "script.py",
            "text/x-python",
            "text/plain",
        ),
        (
            "config.cfg",
            "application/octet-stream",
            "text/plain",
        ),
    ],
)
def test_validate_upload_accepts_supported_real_world_mime_variants(
    settings,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    sniffed_mime: str,
) -> None:
    service = _service(settings)
    extension = "." + filename.rsplit(".", 1)[-1]
    if extension not in settings.upload_allowed_extensions:
        settings.upload_allowed_extensions.append(extension)
    if content_type not in settings.upload_allowed_mime_types:
        settings.upload_allowed_mime_types.append(content_type)
    monkeypatch.setitem(
        sys.modules,
        "magic",
        SimpleNamespace(from_buffer=lambda *_args, **_kwargs: sniffed_mime),
    )

    service._validate_upload(
        filename=filename,
        content_type=content_type,
        payload=b"placeholder",
    )


@pytest.mark.parametrize(
    ("filename", "content_type", "sniffed_mime"),
    [
        (
            "report.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "deck.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        (
            "sheet.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_validate_upload_accepts_canonical_ooxml_mime_types(
    settings,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    sniffed_mime: str,
) -> None:
    service = _service(settings)
    extension = "." + filename.rsplit(".", 1)[-1]
    if extension not in settings.upload_allowed_extensions:
        settings.upload_allowed_extensions.append(extension)
    if content_type not in settings.upload_allowed_mime_types:
        settings.upload_allowed_mime_types.append(content_type)
    monkeypatch.setitem(
        sys.modules,
        "magic",
        SimpleNamespace(from_buffer=lambda *_args, **_kwargs: sniffed_mime),
    )

    service._validate_upload(
        filename=filename,
        content_type=content_type,
        payload=b"placeholder",
    )


@pytest.mark.parametrize(
    ("filename", "content_type", "sniffed_mime"),
    [
        ("broken.pdf", "application/pdf", "text/plain"),
        ("image.png", "image/png", "application/octet-stream"),
    ],
)
def test_validate_upload_accepts_supported_declared_mime_when_signature_mismatches(
    settings,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content_type: str,
    sniffed_mime: str,
) -> None:
    service = _service(settings)
    extension = "." + filename.rsplit(".", 1)[-1]
    if extension not in settings.upload_allowed_extensions:
        settings.upload_allowed_extensions.append(extension)
    if content_type not in settings.upload_allowed_mime_types:
        settings.upload_allowed_mime_types.append(content_type)
    monkeypatch.setitem(
        sys.modules,
        "magic",
        SimpleNamespace(from_buffer=lambda *_args, **_kwargs: sniffed_mime),
    )

    service._validate_upload(
        filename=filename,
        content_type=content_type,
        payload=b"placeholder",
    )


def test_enqueue_ingestion_queue_unavailable(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(settings)

    class _Task:
        @staticmethod
        def delay(*args, **kwargs):  # type: ignore[no-untyped-def]
            _ = (args, kwargs)
            raise RuntimeError("queue down")

    monkeypatch.setattr("app.worker.tasks_ingestion.process_ingestion_job", _Task)
    with pytest.raises(ApiError) as exc:
        service._enqueue_ingestion(job_id=uuid4(), tenant_id=uuid4())
    assert exc.value.code == "INGESTION_QUEUE_UNAVAILABLE"


def test_upload_document_storage_error_maps_to_api_error(settings) -> None:
    service = _service(settings)
    tenant_id = uuid4()
    user_id = uuid4()
    service._validate_upload = lambda **kwargs: None  # type: ignore[method-assign]
    service.idempotency = SimpleNamespace(
        compute_fingerprint=lambda **kwargs: "fp",
        check_replay_or_conflict=lambda **kwargs: None,
    )
    service.malware = SimpleNamespace(
        scan_bytes=lambda **kwargs: SimpleNamespace(is_clean=True, reason=None)
    )
    service.storage = SimpleNamespace(
        put_bytes=lambda **kwargs: (_ for _ in ()).throw(
            StorageServiceError(
                code="STORAGE_UNAVAILABLE", message="down", retryable=True
            )
        )
    )
    service.documents = SimpleNamespace(
        create=lambda *args, **kwargs: None,
        get_by_hash=lambda **kwargs: None,
        get_latest_by_filename=lambda **kwargs: None,
    )
    service.jobs = SimpleNamespace(create=lambda *args, **kwargs: None)

    with pytest.raises(ApiError) as exc:
        service.upload_document(
            auth=SimpleNamespace(tenant_id=tenant_id, user_id=user_id),
            idempotency_key="idem",
            filename="x.pdf",
            content_type="application/pdf",
            payload=b"ok",
        )
    assert exc.value.code == "STORAGE_UNAVAILABLE"


def test_compute_retry_delay_uses_backoff_and_jitter(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _service(settings)
    settings.ingestion_retry_backoff_seconds = 5
    monkeypatch.setattr(
        "app.ingestion.services.ingestion_service.secrets.randbelow", lambda n: n - 1
    )
    delay = service.compute_retry_delay(current_attempt=3)
    assert delay == (5 * (2**2)) + 5
