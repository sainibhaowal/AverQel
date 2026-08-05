from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import redis
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.chunk_embedding import ChunkEmbedding
from app.documents.models.document import Document
from app.documents.models.document_chunk import DocumentChunk
from app.documents.repositories.chunks import ChunksRepository
from app.documents.repositories.documents import DocumentsRepository
from app.ingestion.models.ingestion_job import IngestionJob
from app.ingestion.repositories.ingestion_jobs import IngestionJobsRepository
from app.ingestion.services.chunking_service import ChunkingService
from app.ingestion.services.embedding_service import EmbeddingService
from app.ingestion.services.extraction_quality import (
    confidence_band,
    fallback_reasons,
    normalize_warnings,
)
from app.ingestion.services.extractors.base import ExtractionResult
from app.ingestion.services.extractors.router import ExtractorRouter
from app.ingestion.services.parser_service import ParserService, sanitize_document_text
from app.ingestion.services.security.malware_scan_service import MalwareScanService
from app.system.repositories.idempotency_keys import IdempotencyKeysRepository
from app.system.services.idempotency_service import IdempotencyService
from app.system.services.metrics_service import (
    EXTRACTION_FAILURE_TOTAL,
    EXTRACTION_FALLBACK_TOTAL,
    EXTRACTION_LOW_CONFIDENCE_TOTAL,
    EXTRACTION_METHOD_TOTAL,
    QUERY_PIPELINE_DURATION_SECONDS,
    WORKER_DEAD_LETTER_TOTAL,
    WORKER_JOB_TRANSITIONS_TOTAL,
    WORKER_RETRIES_TOTAL,
    WORKER_STAGE_DURATION_SECONDS,
    observe_extraction_stage,
)
from app.system.services.storage_service import StorageService, StorageServiceError

logger = logging.getLogger(__name__)
UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class RetryableIngestionError(Exception):
    pass


@dataclass(slots=True)
class UploadResult:
    document_id: uuid.UUID
    status: str
    ingestion_job_id: uuid.UUID


@dataclass(slots=True)
class DocumentStatusResult:
    document_id: uuid.UUID
    status: str
    processing_progress: int
    quarantined: bool
    information_yield: float | None
    ingestion_job_id: uuid.UUID | None
    ingestion_status: str | None
    attempt_count: int | None
    max_attempts: int | None
    last_error_code: str | None
    last_error_message: str | None
    dead_lettered_at: datetime | None
    extraction_method: str | None
    extraction_coverage_score: float | None
    extraction_ocr_used: bool
    extraction_vision_used: bool
    extraction_warnings: list[str]
    extraction_confidence_band: str
    embedding_provider: str | None
    embedding_model: str | None
    embedded_chunk_count: int
    active_stage: str
    stage_progress: int


class IngestionService:
    STALE_QUEUE_RECOVERY_AFTER = timedelta(minutes=2)
    _TEXT_LIKE_EXTENSIONS = frozenset({".txt", ".md"})
    _CODE_LIKE_EXTENSIONS = frozenset(
        {
            ".py",
            ".js",
            ".ts",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".cs",
            ".php",
            ".rb",
            ".swift",
            ".kt",
            ".scala",
            ".sql",
            ".yaml",
            ".yml",
            ".json",
            ".xml",
            ".html",
            ".css",
            ".sh",
            ".toml",
            ".ini",
            ".cfg",
            ".log",
            ".csv",
            ".tsv",
            ".ipynb",
        }
    )
    _IMAGE_EXTENSIONS = frozenset(
        {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp", ".gif"}
    )
    _OOXML_EXTENSIONS = frozenset({".docx", ".pptx", ".xlsx"})
    _OOXML_EXTENSION_MIME_TYPES = {
        ".docx": frozenset(
            {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        ),
        ".pptx": frozenset(
            {"application/vnd.openxmlformats-officedocument.presentationml.presentation"}
        ),
        ".xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    }
    _LEGACY_OFFICE_EXTENSIONS = frozenset({".doc", ".ppt", ".xls"})
    _ZIP_MIME_TYPES = frozenset(
        {"application/zip", "application/x-zip-compressed", "application/octet-stream"}
    )
    _GENERIC_BINARY_MIME_TYPES = frozenset(
        {
            "application/octet-stream",
            "application/x-empty",
            "application/x-ole-storage",
            "application/vnd.ms-office",
            "application/CDFV2",
            "application/x-cdf",
            "application/x-composite-document-file",
        }
    )
    _STAGE_PROGRESS_RANGES: dict[str, tuple[int, int]] = {
        "queued": (0, 5),
        "downloading": (5, 10),
        "parsing": (10, 30),
        "chunking": (30, 60),
        "embedding": (60, 95),
        "indexed": (95, 100),
        "completed": (95, 100),
        "failed": (0, 0),
        "dead_lettered": (0, 0),
    }

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        storage_service: StorageService | None = None,
        malware_scan_service: MalwareScanService | None = None,
        parser_service: ParserService | None = None,
        extractor_router: ExtractorRouter | None = None,
        chunking_service: ChunkingService | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.documents = DocumentsRepository(db)
        self.jobs = IngestionJobsRepository(db)
        self.chunks = ChunksRepository(db)
        self.idempotency = IdempotencyService(IdempotencyKeysRepository(db))
        self.storage = storage_service or StorageService(settings)
        self.malware = malware_scan_service or MalwareScanService()
        self.parser = parser_service or ParserService()
        self.extractor_router = extractor_router or ExtractorRouter(settings=settings)
        self.chunking = chunking_service or ChunkingService()
        self.embedding = embedding_service or EmbeddingService(settings, db=db)
        self.redis = cast(redis.Redis, redis.from_url(settings.redis_url))  # type: ignore[no-untyped-call]

    def upload_document(
        self,
        *,
        auth: AuthContext,
        idempotency_key: str,
        filename: str,
        content_type: str,
        payload: bytes,
        connector_id: uuid.UUID | None = None,
    ) -> UploadResult:
        self._validate_upload(filename=filename, content_type=content_type, payload=payload)
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        request_fingerprint = self.idempotency.compute_fingerprint(
            payload_sha256=payload_sha256,
            filename=filename,
            content_type=content_type,
            size_bytes=len(payload),
        )
        replay = self.idempotency.check_replay_or_conflict(
            tenant_id=auth.tenant_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if replay is not None:
            return UploadResult(
                document_id=uuid.UUID(str(replay.response_body["document_id"])),
                status=str(replay.response_body["status"]),
                ingestion_job_id=uuid.UUID(str(replay.response_body["ingestion_job_id"])),
            )

        # Content Deduplication
        existing = self.documents.get_by_hash(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            sha256_hash=payload_sha256,
        )
        if existing:
            # If document already exists and is indexed, we can just return it.
            # We skip creating a new job and new storage entry.
            logger.info(
                "Deduplicated document upload by hash",
                extra={"document_id": str(existing.id), "hash": payload_sha256},
            )

            # Check for related job
            existing_job = self.jobs.get_by_document_id(
                tenant_id=auth.tenant_id, document_id=existing.id
            )

            return UploadResult(
                document_id=existing.id,
                status=existing.status,
                ingestion_job_id=(
                    existing_job.id if existing_job else uuid.UUID(int=0)
                ),  # 0 UUID if no job (shouldn't happen)
            )

        scan = self.malware.scan_bytes(
            filename=filename,
            content_type=content_type,
            payload=payload,
        )
        if not scan.is_clean:
            raise ApiError(
                code="MALWARE_SCAN_FAILED",
                message="Uploaded file was blocked by malware scanner.",
                status_code=422,
                details={"reason": scan.reason or "scan_failed"},
            )

        document_id = generate_uuid7_with_fallback()
        safe_filename = Path(filename).name

        # Versioning Detection
        latest_version = self.documents.get_latest_by_filename(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            filename=safe_filename,
        )
        parent_id = None
        current_version = 1

        if latest_version:
            parent_id = latest_version.id
            current_version = latest_version.version + 1
            logger.info(
                "New document version detected",
                extra={
                    "filename": safe_filename,
                    "previous_id": str(parent_id),
                    "new_version": current_version,
                },
            )

        try:
            stored = self.storage.put_bytes(
                tenant_id=auth.tenant_id,
                document_id=document_id,
                filename=safe_filename,
                content_type=content_type,
                payload=payload,
            )
        except StorageServiceError as exc:
            raise ApiError(
                code=exc.code,
                message=exc.message,
                status_code=503,
            ) from exc

        document = Document(
            id=document_id,
            tenant_id=auth.tenant_id,
            uploaded_by_user_id=auth.user_id,
            filename=safe_filename,
            content_type=content_type,
            size_bytes=len(payload),
            sha256_hash=payload_sha256,
            storage_bucket=stored.bucket,
            storage_object_key=stored.object_key,
            status="queued",
            parent_document_id=parent_id,
            version=current_version,
            connector_id=connector_id,
        )
        self.documents.create(document)

        job = IngestionJob(
            id=generate_uuid7_with_fallback(),
            tenant_id=auth.tenant_id,
            document_id=document.id,
            status="queued",
            attempt_count=0,
            max_attempts=self.settings.ingestion_max_attempts,
        )
        self.jobs.create(job)

        response_body = {
            "document_id": str(document.id),
            "status": "queued",
            "ingestion_job_id": str(job.id),
        }
        self.idempotency.persist_result(
            tenant_id=auth.tenant_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            resource_type="document_upload",
            resource_id=document.id,
            status_code=200,
            response_body=response_body,
        )

        document_id = document.id
        job_id = job.id

        heavy_extensions = {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".tif",
            ".bmp",
            ".webp",
            ".docx",
            ".pptx",
            ".xlsx",
            ".doc",
            ".ppt",
            ".xls",
        }
        queue_name = (
            "ingestion_heavy"
            if Path(filename).suffix.lower() in heavy_extensions
            else "ingestion_light"
        )

        self.db.commit()
        self._enqueue_ingestion(job_id=job_id, tenant_id=auth.tenant_id, queue=queue_name)
        return UploadResult(document_id=document_id, status="queued", ingestion_job_id=job_id)

    def get_document(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> Document:
        document = (
            self.documents.get_accessible_by_id(
                tenant_id=tenant_id,
                document_id=document_id,
                user_id=user_id,
                include_quarantined=True,
            )
            if user_id is not None
            else self.documents.get_by_id(tenant_id=tenant_id, document_id=document_id)
        )
        if document is None:
            raise ApiError(
                code="DOCUMENT_NOT_FOUND",
                message="Document was not found for tenant.",
                status_code=404,
            )
        return document

    def get_document_status(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> DocumentStatusResult:
        document = self.get_document(
            tenant_id=tenant_id,
            document_id=document_id,
            user_id=user_id,
        )
        job = self.jobs.get_by_document_id(tenant_id=tenant_id, document_id=document_id)
        if job is not None:
            self._recover_stale_queued_job_if_needed(
                tenant_id=tenant_id,
                document=document,
                job=job,
            )
        embedding_summary = self.chunks.get_embedding_summary_by_document_id(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        active_stage = self._normalize_pipeline_stage(
            job.status if job is not None else document.status
        )
        return DocumentStatusResult(
            document_id=document.id,
            status=document.status,
            processing_progress=document.processing_progress,
            quarantined=document.quarantined,
            information_yield=document.information_yield,
            ingestion_job_id=job.id if job else None,
            ingestion_status=job.status if job else None,
            attempt_count=job.attempt_count if job else None,
            max_attempts=job.max_attempts if job else None,
            last_error_code=job.last_error_code if job else None,
            last_error_message=job.last_error_message if job else None,
            dead_lettered_at=job.dead_lettered_at if job else None,
            extraction_method=document.extraction_method,
            extraction_coverage_score=document.extraction_coverage_score,
            extraction_ocr_used=document.extraction_ocr_used,
            extraction_vision_used=document.extraction_vision_used,
            extraction_warnings=list(document.extraction_warnings or []),
            extraction_confidence_band=confidence_band(document.extraction_coverage_score),
            embedding_provider=(
                embedding_summary.provider if embedding_summary is not None else None
            ),
            embedding_model=(embedding_summary.model if embedding_summary is not None else None),
            embedded_chunk_count=(
                embedding_summary.embedded_chunk_count if embedding_summary is not None else 0
            ),
            active_stage=active_stage,
            stage_progress=self._compute_stage_progress(
                active_stage=active_stage,
                overall_progress=document.processing_progress,
            ),
        )

    def _recover_stale_queued_job_if_needed(
        self,
        *,
        tenant_id: uuid.UUID,
        document: Document,
        job: IngestionJob,
    ) -> None:
        if document.status != "queued" or job.status != "queued":
            return
        if document.processing_progress > 0 or job.attempt_count > 0:
            return
        now = datetime.now(tz=UTC)
        last_update = max(document.updated_at, job.updated_at)
        if now - last_update < self.STALE_QUEUE_RECOVERY_AFTER:
            return

        queue_name = self._choose_ingestion_queue(document.filename)
        job.updated_at = now
        document.updated_at = now
        self.db.commit()
        self._enqueue_ingestion(
            job_id=job.id,
            tenant_id=tenant_id,
            queue=queue_name,
        )
        self._publish_update(
            tenant_id,
            document.id,
            "queued",
            getattr(document, "processing_progress", 0),
        )

    def _publish_update(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, status: str, progress: int
    ) -> None:
        """Broadcast update via Redis PubSub for real-time SSE."""
        redis_client = getattr(self, "redis", None)
        if redis_client is None:
            return
        active_stage = self._normalize_pipeline_stage(status)
        try:
            document = self.documents.get_by_id(
                tenant_id=tenant_id,
                document_id=document_id,
            )
            if document is None:
                return
        except Exception:
            logger.warning("Failed to load document status for Redis update", exc_info=True)
            return
        published_status = document.status or status
        published_progress = document.processing_progress
        active_stage = self._normalize_pipeline_stage(published_status)
        message = json.dumps(
            {
                "document_id": str(document_id),
                "status": published_status,
                "progress": published_progress,
                "active_stage": active_stage,
                "stage_progress": self._compute_stage_progress(
                    active_stage=active_stage,
                    overall_progress=published_progress,
                ),
                "updated_at": (
                    document.updated_at.isoformat() if document.updated_at is not None else None
                ),
            }
        )
        try:
            redis_client.publish(
                f"document_updates:{tenant_id}:{document.uploaded_by_user_id}",
                message,
            )
        except Exception:
            logger.warning("Failed to publish real-time update to Redis", exc_info=True)

    def process_ingestion_job(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        overall_start = time.perf_counter()
        job = self.jobs.get_by_id(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.warning("ingestion job not found", extra={"job_id": str(job_id)})
            return
        document = self.documents.get_by_id(tenant_id=tenant_id, document_id=job.document_id)
        if document is None:
            self.jobs.set_status(
                tenant_id=tenant_id,
                job=job,
                status="dead_lettered",
                error_code="DOCUMENT_NOT_FOUND",
                error_message="Related document is missing.",
            )
            self.db.commit()
            return

        latest_job = self.jobs.get_by_document_id(tenant_id=tenant_id, document_id=document.id)
        if latest_job is not None and latest_job.id != job.id:
            self.jobs.set_status(
                tenant_id=tenant_id,
                job=job,
                status="failed",
                error_code="SUPERSEDED_JOB",
                error_message="A newer ingestion job exists for this document.",
            )
            self.db.commit()
            return

        if document.status == "indexed":
            self.jobs.set_status(
                tenant_id=tenant_id,
                job=job,
                status="indexed",
            )
            self.db.commit()
            return

        self.jobs.increment_attempt(tenant_id=tenant_id, job=job)

        try:
            stage_start = time.perf_counter()
            self.jobs.set_status(tenant_id=tenant_id, job=job, status="downloading")
            self._set_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                status="downloading",
                progress=5,
            )
            payload = self.storage.get_bytes(
                bucket=document.storage_bucket,
                object_key=document.storage_object_key,
            )
            WORKER_STAGE_DURATION_SECONDS.labels(stage="downloading").observe(
                time.perf_counter() - stage_start
            )
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="downloading", status="success").inc()

            stage_start = time.perf_counter()
            self.jobs.set_status(tenant_id=tenant_id, job=job, status="parsing")
            self._set_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                status="parsing",
                progress=10,
            )
            extraction = self._extract_document_text(
                tenant_id=tenant_id,
                filename=document.filename,
                content_type=document.content_type,
                payload=payload,
            )
            extraction.warnings = normalize_warnings(extraction.warnings)
            EXTRACTION_METHOD_TOTAL.labels(method=extraction.extraction_method).inc()
            for path, reason in fallback_reasons(extraction):
                EXTRACTION_FALLBACK_TOTAL.labels(path=path, reason=reason).inc()
            if extraction.coverage_score < self.settings.ocr_min_confidence:
                EXTRACTION_LOW_CONFIDENCE_TOTAL.labels(
                    band=confidence_band(extraction.coverage_score)
                ).inc()
            self.documents.set_extraction_metadata(
                tenant_id=tenant_id,
                document=document,
                extraction=extraction,
            )
            if not extraction.text.strip():
                raise ApiError(
                    code="DOCUMENT_EMPTY_AFTER_PARSE",
                    message="Document does not contain parseable text.",
                    status_code=422,
                )

            try:
                import langdetect  # type: ignore[import-untyped]

                # Detect language based on first 5000 characters to save CPU
                document.language = langdetect.detect(extraction.text[:5000])
            except Exception as e:
                logger.warning(f"Language detection failed for document {document.id}: {e}")
                document.language = "unknown"
            self._set_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                status="parsing",
                progress=25,
            )
            WORKER_STAGE_DURATION_SECONDS.labels(stage="parsing").observe(
                time.perf_counter() - stage_start
            )
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="parsing", status="success").inc()

            stage_start = time.perf_counter()
            self.jobs.set_status(tenant_id=tenant_id, job=job, status="chunking")
            self._set_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                status="chunking",
                progress=30,
            )
            with observe_extraction_stage("chunk"):
                chunk_mode = self._chunk_mode_for_extraction(
                    extraction_method=extraction.extraction_method,
                    filename=document.filename,
                )
                if extraction.layout_blocks:
                    parts = self.chunking.chunk_structured(
                        blocks=extraction.layout_blocks,
                        chunk_size=self.settings.chunk_size,
                        overlap=self.settings.chunk_overlap,
                        min_length=self.settings.chunk_min_length,
                    )
                    # For structured chunking, layout_vision is the implicit mode
                    for p in parts:
                        p.metadata["mode"] = "vision"
                else:
                    parts = self.chunking.chunk(
                        extraction.text,
                        chunk_size=self.settings.chunk_size,
                        overlap=self.settings.chunk_overlap,
                        min_length=self.settings.chunk_min_length,
                        mode=chunk_mode,
                        source_metadata={
                            "mode": "ocr" if extraction.ocr_used else chunk_mode,
                            "extraction_method": extraction.extraction_method,
                        },
                    )
            if not parts:
                raise ApiError(
                    code="NO_VALID_CHUNKS",
                    message="Document did not produce valid chunks.",
                    status_code=422,
                )

            chunk_rows: list[DocumentChunk] = []
            total_parts = max(len(parts), 1)
            for part in parts:
                safe_content = sanitize_document_text(part.content).strip()
                if not safe_content:
                    continue
                chunk_rows.append(
                    DocumentChunk(
                        id=generate_uuid7_with_fallback(),
                        tenant_id=tenant_id,
                        document_id=document.id,
                        chunk_index=part.chunk_index,
                        content=safe_content,
                        char_start=part.char_start,
                        char_end=part.char_end,
                        chunk_metadata=part.metadata,
                    )
                )
                self._set_progress(
                    tenant_id=tenant_id,
                    document_id=document.id,
                    status="chunking",
                    progress=self._scaled_progress(
                        stage="chunking",
                        current=len(chunk_rows),
                        total=total_parts,
                    ),
                )
            if not chunk_rows:
                raise ApiError(
                    code="NO_VALID_CHUNKS",
                    message="Document did not produce valid chunks.",
                    status_code=422,
                )
            chunk_rows = self.chunks.replace_document_chunks(
                tenant_id=tenant_id,
                document_id=document.id,
                chunks=chunk_rows,
            )
            self._set_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                status="chunking",
                progress=60,
            )
            WORKER_STAGE_DURATION_SECONDS.labels(stage="chunking").observe(
                time.perf_counter() - stage_start
            )
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="chunking", status="success").inc()

            stage_start = time.perf_counter()
            self.jobs.set_status(tenant_id=tenant_id, job=job, status="embedding")
            self._set_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                status="embedding",
                progress=60,
            )
            embedding_metadata = None
            try:
                vectors: list[list[float]] = []
                batch_size = max(self.settings.embedding_batch_size, 1)
                total_batches = max(
                    (len(chunk_rows) + batch_size - 1) // batch_size,
                    1,
                )
                for batch_index, start in enumerate(
                    range(0, len(chunk_rows), batch_size),
                    start=1,
                ):
                    batch_rows = chunk_rows[start : start + batch_size]
                    embedding_result = self.embedding.embed_many_with_metadata(
                        [row.content for row in batch_rows],
                        tenant_id=document.tenant_id,
                        actor_user_id=getattr(document, "uploaded_by_user_id", None),
                    )
                    vectors.extend(embedding_result.vectors)
                    if embedding_metadata is None:
                        embedding_metadata = embedding_result.metadata
                    self._set_progress(
                        tenant_id=tenant_id,
                        document_id=document.id,
                        status="embedding",
                        progress=self._scaled_progress(
                            stage="embedding",
                            current=batch_index,
                            total=total_batches,
                        ),
                    )
            except TypeError as exc:
                if not any(token in str(exc) for token in ("tenant_id", "actor_user_id")):
                    raise
                # Preserve compatibility with older test doubles patched against
                # intermediate embed_many_with_metadata(texts, tenant_id=...) and
                # older pre-selection embed_many(texts) signatures.
                try:
                    embedding_result = self.embedding.embed_many_with_metadata(
                        [row.content for row in chunk_rows],
                        tenant_id=document.tenant_id,
                    )
                    vectors = embedding_result.vectors
                    embedding_metadata = embedding_result.metadata
                except TypeError as fallback_exc:
                    if "tenant_id" not in str(fallback_exc):
                        raise
                    vectors = self.embedding.embed_many([row.content for row in chunk_rows])
                    embedding_metadata = None

            embedding_rows: list[ChunkEmbedding] = []
            embedding_provider = (
                embedding_metadata.provider
                if embedding_metadata is not None
                else self.settings.embedding_provider
            )
            embedding_model = (
                embedding_metadata.model
                if embedding_metadata is not None
                else self.settings.embedding_model
            )
            for row, vector in zip(chunk_rows, vectors, strict=True):
                embedding_rows.append(
                    ChunkEmbedding(
                        id=generate_uuid7_with_fallback(),
                        tenant_id=tenant_id,
                        document_id=document.id,
                        chunk_id=row.id,
                        embedding=vector,
                        provider=embedding_provider,
                        model=embedding_model,
                    )
                )
            self.chunks.replace_chunk_embeddings(
                tenant_id=tenant_id,
                document_id=document.id,
                embeddings=embedding_rows,
            )
            WORKER_STAGE_DURATION_SECONDS.labels(stage="embedding").observe(
                time.perf_counter() - stage_start
            )
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="embedding", status="success").inc()

            # ── Yield & Quarantine Calculation ──────────────────────────
            total_detected = len(parts) if parts else 1
            successfully_embedded = len(embedding_rows)
            coverage = extraction.coverage_score if extraction.coverage_score else 1.0
            information_yield = round((successfully_embedded / total_detected) * coverage * 100, 2)
            document.information_yield = information_yield
            document.processing_progress = 100
            if information_yield < 50.0:
                document.quarantined = True
                logger.warning(
                    "document %s quarantined: yield=%.1f%%",
                    document.id,
                    information_yield,
                )

            self.jobs.set_status(tenant_id=tenant_id, job=job, status="indexed")
            self.documents.set_processing_progress(
                tenant_id=tenant_id,
                document_id=document.id,
                progress=100,
                status="indexed",
            )
            self._publish_update(tenant_id, document.id, "indexed", 100)
            self.db.commit()
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="indexed", status="success").inc()
            QUERY_PIPELINE_DURATION_SECONDS.labels(segment="ingestion_total").observe(
                time.perf_counter() - overall_start
            )
        except StorageServiceError as exc:
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="downloading", status="error").inc()
            self._handle_failure(
                tenant_id=tenant_id,
                document=document,
                job=job,
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
            )
        except ApiError as exc:
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="ingestion", status="error").inc()
            retryable_codes = {
                "EMBEDDING_PROVIDER_UNAVAILABLE",
                "EMBEDDING_CIRCUIT_OPEN",
                "PROVIDER_CIRCUIT_OPEN",
                "STORAGE_UNAVAILABLE",
            }
            self._handle_failure(
                tenant_id=tenant_id,
                document=document,
                job=job,
                code=exc.code,
                message=exc.message,
                retryable=exc.code in retryable_codes or exc.status_code >= 500,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("unhandled ingestion failure", exc_info=exc)
            WORKER_JOB_TRANSITIONS_TOTAL.labels(stage="ingestion", status="error").inc()
            self._handle_failure(
                tenant_id=tenant_id,
                document=document,
                job=job,
                code="INGESTION_UNEXPECTED_ERROR",
                message="Unhandled ingestion failure.",
                retryable=True,
            )

    def compute_retry_delay(self, *, current_attempt: int) -> int:
        base = self.settings.ingestion_retry_backoff_seconds
        exponent = max(current_attempt - 1, 0)
        delay = base * (2**exponent)
        jitter = secrets.randbelow(max(base, 1) + 1)
        return int(delay + jitter)

    def _handle_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        document: Document,
        job: IngestionJob,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        # A failure can happen after SQLAlchemy has already marked the
        # transaction as failed (for example during a flush). Reset the
        # session before reading or mutating ORM objects so failure handling
        # can persist the retry/dead-letter state instead of raising a
        # secondary PendingRollbackError and leaving the job queued forever.
        try:
            self.db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Ingestion failure rollback failed.", exc_info=True)

        EXTRACTION_FAILURE_TOTAL.labels(code=code).inc()
        if retryable and job.attempt_count < job.max_attempts:
            self.jobs.set_status(
                tenant_id=tenant_id,
                job=job,
                status="failed",
                error_code=code,
                error_message=message,
            )
            self.documents.set_status(tenant_id=tenant_id, document=document, status="failed")
            self.db.commit()
            self._publish_update(
                tenant_id,
                document.id,
                "failed",
                getattr(document, "processing_progress", 0),
            )
            WORKER_RETRIES_TOTAL.labels(stage="ingestion").inc()
            raise RetryableIngestionError(message)

        status = "dead_lettered" if retryable else "failed"
        self.jobs.set_status(
            tenant_id=tenant_id,
            job=job,
            status=status,
            error_code=code,
            error_message=message,
        )
        self.documents.set_status(
            tenant_id=tenant_id,
            document=document,
            status=status,
        )
        self.db.commit()
        self._publish_update(
            tenant_id,
            document.id,
            status,
            getattr(document, "processing_progress", 0),
        )
        if status == "dead_lettered":
            WORKER_DEAD_LETTER_TOTAL.labels(stage="ingestion").inc()

    async def set_processing_progress(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        progress: int,
        status: str | None = None,
    ) -> None:
        self.documents.set_processing_progress(
            tenant_id=tenant_id,
            document_id=document_id,
            progress=progress,
            status=status,
        )
        self.db.commit()
        # Emit signal for SSE
        if status:
            self._publish_update(tenant_id, document_id, status, progress)

    def list_documents(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> list[Document]:
        items = (
            self.documents.list_accessible_for_user(
                tenant_id=tenant_id,
                user_id=user_id,
                include_quarantined=True,
            )
            if user_id is not None
            else self.documents.list_by_tenant(tenant_id=tenant_id)
        )
        jobs = self.jobs.get_by_document_ids(
            tenant_id=tenant_id,
            document_ids=[item.id for item in items],
        )
        for item in items:
            job = jobs.get(item.id)
            if job is not None:
                self._recover_stale_queued_job_if_needed(
                    tenant_id=tenant_id,
                    document=item,
                    job=job,
                )
        return items

    def _set_progress(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        progress: int,
        status: str,
    ) -> None:
        clamped = max(0, min(progress, 100))
        self.documents.set_processing_progress(
            tenant_id=tenant_id,
            document_id=document_id,
            progress=clamped,
            status=status,
        )
        self.db.commit()
        self._publish_update(tenant_id, document_id, status, clamped)

    def _scaled_progress(self, *, stage: str, current: int, total: int) -> int:
        start, end = self._STAGE_PROGRESS_RANGES.get(stage, (0, 100))
        if total <= 0:
            return start
        bounded_current = max(0, min(current, total))
        if bounded_current == 0:
            return start
        span = max(end - start, 1)
        return min(end, start + round((bounded_current / total) * span))

    def _normalize_pipeline_stage(self, status: str | None) -> str:
        normalized = (status or "queued").lower()
        if normalized in {"completed", "indexed"}:
            return "indexed"
        if normalized == "downloading":
            return "queued"
        if normalized in {"queued", "parsing", "chunking", "embedding"}:
            return normalized
        return "queued"

    def _compute_stage_progress(self, *, active_stage: str, overall_progress: int) -> int:
        start, end = self._STAGE_PROGRESS_RANGES.get(active_stage, (0, 100))
        if end <= start:
            return 100 if active_stage == "indexed" else 0
        normalized = max(start, min(overall_progress, end))
        return round(((normalized - start) / (end - start)) * 100)

    def _validate_upload(self, *, filename: str, content_type: str, payload: bytes) -> None:
        if not filename.strip():
            raise ApiError(
                code="INVALID_UPLOAD_FILENAME",
                message="Uploaded filename is required.",
                status_code=400,
            )

        extension = Path(filename).suffix.lower()
        if extension not in {ext.lower() for ext in self.settings.upload_allowed_extensions}:
            raise ApiError(
                code="INVALID_UPLOAD_TYPE",
                message="Uploaded file extension is not allowed.",
                status_code=400,
                details={"allowed_extensions": self.settings.upload_allowed_extensions},
            )

        import magic

        sniffed_mime = magic.from_buffer(payload, mime=True)
        declared_mime_allowed = self._is_mime_compatible_with_extension(
            extension=extension, mime_type=content_type
        )
        sniffed_mime_allowed = self._is_mime_compatible_with_extension(
            extension=extension, mime_type=sniffed_mime
        )

        if not declared_mime_allowed and not sniffed_mime_allowed:
            raise ApiError(
                code="INVALID_UPLOAD_TYPE",
                message="Uploaded file MIME type is not allowed.",
                status_code=400,
                details={
                    "allowed_mime_types": self.settings.upload_allowed_mime_types,
                    "content_type": content_type,
                    "sniffed_mime": sniffed_mime,
                },
            )
        if declared_mime_allowed and not sniffed_mime_allowed:
            logger.info(
                "Tolerating upload signature mismatch for supported format",
                extra={
                    "upload_filename": filename,
                    "upload_content_type": content_type,
                    "upload_sniffed_mime": sniffed_mime,
                },
            )
        if len(payload) > self.settings.upload_max_bytes:
            raise ApiError(
                code="DOC_TOO_LARGE",
                message="Uploaded file exceeds maximum allowed size.",
                status_code=413,
                details={"max_bytes": self.settings.upload_max_bytes},
            )

        from app.ingestion.services.security.archive_security import ArchiveSecurityService

        ArchiveSecurityService().validate_payload(filename=filename, payload=payload)

    def _is_mime_compatible_with_extension(self, *, extension: str, mime_type: str | None) -> bool:
        normalized = (mime_type or "").strip().lower()
        if not normalized:
            return False

        if extension == ".pdf":
            return normalized == "application/pdf"

        if extension in self._IMAGE_EXTENSIONS:
            return normalized.startswith("image/")

        if extension in self._TEXT_LIKE_EXTENSIONS | self._CODE_LIKE_EXTENSIONS:
            return (
                normalized.startswith("text/")
                or normalized
                in {
                    "application/json",
                    "application/xml",
                    "text/xml",
                    "text/csv",
                    "text/tab-separated-values",
                    "application/x-ipynb+json",
                    "application/x-sh",
                    "application/javascript",
                    "application/typescript",
                }
                or normalized in self._GENERIC_BINARY_MIME_TYPES
            )

        if extension in self._OOXML_EXTENSIONS:
            return normalized in self._ZIP_MIME_TYPES | self._OOXML_EXTENSION_MIME_TYPES.get(
                extension, frozenset()
            )

        if extension in self._LEGACY_OFFICE_EXTENSIONS:
            return normalized in self._GENERIC_BINARY_MIME_TYPES

        return False

    def _enqueue_ingestion(
        self, *, job_id: uuid.UUID, tenant_id: uuid.UUID, queue: str = "ingestion_light"
    ) -> None:
        from app.ingestion.workers.tasks import process_ingestion_job

        try:
            process_ingestion_job.apply_async(args=(str(job_id), str(tenant_id)), queue=queue)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                code="INGESTION_QUEUE_UNAVAILABLE",
                message="Unable to enqueue ingestion job.",
                status_code=503,
            ) from exc

    @staticmethod
    def _choose_ingestion_queue(filename: str | None) -> str:
        extension = Path(filename or "").suffix.lower()
        heavy_extensions = {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".tif",
            ".bmp",
            ".webp",
            ".docx",
            ".pptx",
            ".xlsx",
            ".doc",
            ".ppt",
            ".xls",
        }
        return "ingestion_heavy" if extension in heavy_extensions else "ingestion_light"

    def _extract_document_text(
        self,
        *,
        tenant_id: uuid.UUID | None,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> ExtractionResult:
        if hasattr(self, "extractor_router"):
            return self.extractor_router.extract(
                filename=filename,
                content_type=content_type,
                payload=payload,
                tenant_id=tenant_id,
            )
        # Backward compatibility for tests that instantiate service via object.__new__.
        parsed = self.parser.parse_bytes(
            filename=filename,
            content_type=content_type,
            payload=payload,
        )
        parsed_text = getattr(parsed, "text", "")
        parsed_page_count = getattr(parsed, "page_count", None)
        return ExtractionResult(
            text=parsed_text,
            page_count=parsed_page_count,
            extraction_method="parser_service",
            coverage_score=1.0 if str(parsed_text).strip() else 0.0,
            warnings=[],
        )

    @staticmethod
    def _chunk_mode_for_extraction(*, extraction_method: str, filename: str) -> str:
        lowered = filename.lower()
        if extraction_method.startswith("xlsx"):
            return "table"
        if extraction_method.startswith("pptx"):
            return "slide"
        if extraction_method.startswith("code") or lowered.endswith(
            (
                ".py",
                ".js",
                ".ts",
                ".java",
                ".go",
                ".rs",
                ".c",
                ".cpp",
                ".cs",
                ".php",
                ".rb",
                ".swift",
                ".kt",
                ".scala",
                ".sql",
                ".yaml",
                ".yml",
                ".json",
                ".xml",
                ".html",
                ".css",
                ".sh",
                ".toml",
                ".ini",
                ".cfg",
                ".log",
            )
        ):
            return "code"
        return "prose"


def make_storage_key(*, tenant_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    safe_name = os.path.basename(filename)
    return f"{tenant_id}/{document_id}/{safe_name}"
