"""Background finalization for durable Library uploads."""

from __future__ import annotations

import logging
import uuid

from celery import Task
from sqlalchemy import select, text

from app.core.config import get_settings
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.services.dataset_derivatives import (
    DatasetDerivativeService,
    safe_dataset_profile,
)
from app.deepspace.services.library_storage import LibraryStorageService
from app.deepspace.services.library_uploads import finalize_upload
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app
from app.system.services.metrics_service import (
    increment_worker_dead_letter,
    increment_worker_retry,
    observe_worker_stage,
)
from app.system.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="deepspace.library_upload_finalize",
    queue="library_uploads",
)  # type: ignore[misc]
def finalize_library_upload(self: Task, *, upload_id: str, tenant_id: str) -> str:
    """Assemble chunks, create the normal Library file, and publish completion in PostgreSQL."""
    del self
    settings = get_settings()
    parsed_upload_id = uuid.UUID(upload_id)
    parsed_tenant_id = uuid.UUID(tenant_id)
    db = get_session_factory()()
    storage = StorageService(settings)
    upload: DeepSpaceLibraryUpload | None = None
    try:
        db.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(db, parsed_tenant_id)
        upload = db.execute(
            select(DeepSpaceLibraryUpload)
            .where(
                DeepSpaceLibraryUpload.id == parsed_upload_id,
                DeepSpaceLibraryUpload.tenant_id == parsed_tenant_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if upload is None:
            return "not-found"
        if upload.status == "cancelled":
            return "cancelled"
        if upload.status == "completed":
            return "completed"
        upload.status = "processing"
        upload.error_message = None
        db.commit()
        chunks = [
            storage.get_upload_chunk(
                tenant_id=parsed_tenant_id,
                upload_id=parsed_upload_id,
                chunk_index=index,
            )
            for index in range(upload.total_chunks)
        ]
        payload = b"".join(chunks)
        # Re-acquire the row lock after the potentially long storage read. A
        # cancel request that arrived while chunks were being assembled must
        # win before we create the final Library record. The lock is held
        # through finalization so cancellation cannot race a completed commit.
        upload = db.execute(
            select(DeepSpaceLibraryUpload)
            .where(
                DeepSpaceLibraryUpload.id == parsed_upload_id,
                DeepSpaceLibraryUpload.tenant_id == parsed_tenant_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if upload is None or upload.status == "cancelled":
            return "cancelled"
        record = finalize_upload(db, settings=settings, upload=upload, payload=payload)
        upload.file_id = record.id
        upload.bytes_received = len(payload)
        upload.received_chunks = list(range(upload.total_chunks))
        upload.status = "completed"
        db.commit()
        if DatasetDerivativeService.supports(record.content_type):
            profile_library_dataset.delay(file_id=str(record.id), tenant_id=tenant_id)
        return str(record.id)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if upload is not None and upload.status != "cancelled":
            upload.status = "failed"
            upload.error_message = str(exc)[:1000]
            try:
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
        logger.exception("Library upload finalization failed", extra={"upload_id": upload_id})
        raise
    finally:
        try:
            if upload is not None and upload.status in {
                "completed",
                "failed",
                "cancelled",
            }:
                storage.delete_upload_chunks(
                    tenant_id=parsed_tenant_id,
                    upload_id=parsed_upload_id,
                    total_chunks=upload.total_chunks,
                )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to clean Library upload chunks", exc_info=True)
        try:
            db.execute(text("RESET ROLE"))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        db.close()


@celery_app.task(
    bind=True,
    name="deepspace.library_dataset_profile",
    queue="dataset_indexing",
    max_retries=3,
)  # type: ignore[misc]
def profile_library_dataset(self: Task, *, file_id: str, tenant_id: str) -> str:
    """Profile structured files off the API path and persist bounded metadata."""
    settings = get_settings()
    parsed_file_id = uuid.UUID(file_id)
    parsed_tenant_id = uuid.UUID(tenant_id)
    db = get_session_factory()()
    try:
        with observe_worker_stage("deepspace_library_dataset_profile"):
            db.execute(text("SET ROLE aks_app"))
            set_db_tenant_context(db, parsed_tenant_id)
            from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

            file = db.execute(
                select(DeepSpaceWorkspaceFile).where(
                    DeepSpaceWorkspaceFile.id == parsed_file_id,
                    DeepSpaceWorkspaceFile.tenant_id == parsed_tenant_id,
                )
            ).scalar_one_or_none()
            if file is None or not DatasetDerivativeService.supports(file.content_type):
                return "skipped"
            payload = (
                LibraryStorageService(settings).storage.get_bytes(
                    bucket=file.storage_bucket, object_key=file.storage_key
                )
                if file.storage_bucket and file.storage_key
                else (file.content or "").encode("utf-8")
            )
            derivative = DatasetDerivativeService(settings).build(
                tenant_id=parsed_tenant_id,
                file_id=file.id,
                filename=file.name,
                content_type=file.content_type,
                payload=payload,
            )
            metadata = dict(file.metadata_json or {})
            metadata["dataset_profile"] = safe_dataset_profile(derivative)
            file.metadata_json = metadata
            db.commit()
            return "profiled"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if self.request.retries < self.max_retries:
            increment_worker_retry(stage="deepspace_library_dataset_profile")
            logger.warning(
                "Library dataset profiling retry scheduled",
                extra={"file_id": file_id, "retry": self.request.retries + 1},
                exc_info=True,
            )
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        increment_worker_dead_letter(stage="deepspace_library_dataset_profile")
        logger.exception("Library dataset profiling exhausted retries", extra={"file_id": file_id})
        try:
            from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

            file = db.execute(
                select(DeepSpaceWorkspaceFile).where(
                    DeepSpaceWorkspaceFile.id == parsed_file_id,
                    DeepSpaceWorkspaceFile.tenant_id == parsed_tenant_id,
                )
            ).scalar_one_or_none()
            if file is not None:
                metadata = dict(file.metadata_json or {})
                metadata["dataset_profile"] = {
                    "status": "failed",
                    "error_code": "DATASET_PARSE_FAILED",
                }
                file.metadata_json = metadata
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise
    finally:
        try:
            db.execute(text("RESET ROLE"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()
