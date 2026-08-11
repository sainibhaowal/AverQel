"""Background finalization for durable Library uploads."""

from __future__ import annotations

import logging
import uuid

from celery import Task
from sqlalchemy import select, text

from app.core.config import get_settings
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.services.library_uploads import finalize_upload
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app
from app.system.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="deepspace.library_upload_finalize")  # type: ignore[misc]
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
            if upload is not None and upload.status in {"completed", "failed", "cancelled"}:
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
