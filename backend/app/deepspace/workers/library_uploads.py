"""Background finalization for durable Library uploads."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import uuid
from typing import Any

from celery import Task
from sqlalchemy import select, text

from app.core.config import get_settings
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.services.dataset_derivatives import (
    DatasetDerivativeService,
    safe_dataset_profile,
)
from app.deepspace.services.library_storage import (
    LibraryStorageService,
    safe_archive_entries,
    safe_extraction_status,
)
from app.deepspace.services.library_uploads import (
    _bounded_extraction_payload,
    finalize_upload,
    unique_library_filename,
)
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
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[misc]
def finalize_library_upload(self: Task, *, upload_id: str, tenant_id: str) -> str:
    """Assemble and publish a Library file without holding locks during storage I/O."""
    from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

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
            completed_file_id = upload.file_id
            db.commit()
            if completed_file_id is not None:
                completed_file = db.execute(
                    select(DeepSpaceWorkspaceFile).where(
                        DeepSpaceWorkspaceFile.id == completed_file_id,
                        DeepSpaceWorkspaceFile.tenant_id == parsed_tenant_id,
                    )
                ).scalar_one_or_none()
                if completed_file is not None:
                    _enqueue_library_file_processing(
                        db,
                        file=completed_file,
                        tenant_id=tenant_id,
                        parsed_tenant_id=parsed_tenant_id,
                    )
                    return str(completed_file.id)
            return "completed"
        total_chunks = upload.total_chunks
        upload.status = "processing"
        upload.error_message = None
        db.commit()
        chunks = [
            storage.get_upload_chunk(
                tenant_id=parsed_tenant_id,
                upload_id=parsed_upload_id,
                chunk_index=index,
            )
            for index in range(total_chunks)
        ]
        payload = b"".join(chunks)
        upload_metadata = upload.metadata_json if isinstance(upload.metadata_json, dict) else {}
        if upload_metadata.get("rename_on_conflict"):
            # Recheck at publication time: another Library write can claim the
            # reserved name after this upload session was created. Keep this
            # row lock short and release it before object-storage work.
            conversation_exists = db.execute(
                select(Conversation.id)
                .where(
                    Conversation.id == upload.conversation_id,
                    Conversation.tenant_id == upload.tenant_id,
                    Conversation.user_id == upload.user_id,
                    Conversation.kind == "deepspace",
                )
                .with_for_update()
            ).scalar_one_or_none()
            if conversation_exists is None:
                db.rollback()
                return "not-found"
            file_name_query = select(DeepSpaceWorkspaceFile.name).where(
                DeepSpaceWorkspaceFile.tenant_id == upload.tenant_id,
                DeepSpaceWorkspaceFile.user_id == upload.user_id,
                DeepSpaceWorkspaceFile.conversation_id == upload.conversation_id,
                (
                    DeepSpaceWorkspaceFile.parent_folder_id.is_(None)
                    if upload.parent_folder_id is None
                    else DeepSpaceWorkspaceFile.parent_folder_id == upload.parent_folder_id
                ),
            )
            reserved_names = set(db.execute(file_name_query).scalars().all())
            active_upload_name_query = select(DeepSpaceLibraryUpload.filename).where(
                DeepSpaceLibraryUpload.tenant_id == upload.tenant_id,
                DeepSpaceLibraryUpload.user_id == upload.user_id,
                DeepSpaceLibraryUpload.conversation_id == upload.conversation_id,
                DeepSpaceLibraryUpload.id != upload.id,
                DeepSpaceLibraryUpload.status.in_(("pending", "uploading", "queued", "processing")),
                (
                    DeepSpaceLibraryUpload.parent_folder_id.is_(None)
                    if upload.parent_folder_id is None
                    else DeepSpaceLibraryUpload.parent_folder_id == upload.parent_folder_id
                ),
            )
            reserved_names.update(db.execute(active_upload_name_query).scalars().all())
            upload.filename = unique_library_filename(upload.filename, reserved_names)
            db.commit()
        # File storage is deliberately done without the upload row lock. Slow
        # object storage or extraction must never block cancellation/status API
        # calls on this transaction.
        record = finalize_upload(
            db,
            settings=settings,
            upload=upload,
            payload=payload,
            extract_content=False,
        )
        upload = db.execute(
            select(DeepSpaceLibraryUpload)
            .where(
                DeepSpaceLibraryUpload.id == parsed_upload_id,
                DeepSpaceLibraryUpload.tenant_id == parsed_tenant_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if upload is None or upload.status == "cancelled":
            stored_bucket = record.storage_bucket
            stored_key = record.storage_key
            db.rollback()
            if stored_bucket and stored_key:
                storage.delete_object(bucket=stored_bucket, object_key=stored_key)
            return "cancelled"
        if upload.status == "completed":
            stored_bucket = record.storage_bucket
            stored_key = record.storage_key
            existing_file_id = upload.file_id
            db.rollback()
            if stored_bucket and stored_key:
                storage.delete_object(bucket=stored_bucket, object_key=stored_key)
            return str(existing_file_id or "completed")
        upload.file_id = record.id
        upload.bytes_received = len(payload)
        upload.received_chunks = list(range(total_chunks))
        upload.status = "completed"
        db.commit()
        _enqueue_library_file_processing(
            db,
            file=record,
            tenant_id=tenant_id,
            parsed_tenant_id=parsed_tenant_id,
        )
        return str(record.id)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if self.request.retries < self.max_retries:
            increment_worker_retry(stage="deepspace_library_upload_finalize")
            logger.warning(
                "Library upload finalization retry scheduled",
                extra={"upload_id": upload_id, "retry": self.request.retries + 1},
                exc_info=True,
            )
            raise self.retry(exc=exc, countdown=min(30, 2 ** (self.request.retries + 1))) from exc
        increment_worker_dead_letter(stage="deepspace_library_upload_finalize")
        try:
            current = db.execute(
                select(DeepSpaceLibraryUpload)
                .where(
                    DeepSpaceLibraryUpload.id == parsed_upload_id,
                    DeepSpaceLibraryUpload.tenant_id == parsed_tenant_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if current is not None and current.status not in {"cancelled", "completed"}:
                current.status = "failed"
                current.error_message = "The file could not be stored. Please retry the upload."
                db.commit()
                upload = current
        except Exception:  # noqa: BLE001
            db.rollback()
        logger.exception(
            "Library upload finalization exhausted retries", extra={"upload_id": upload_id}
        )
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


def _set_library_extraction_status(
    db: Any,
    *,
    file_id: uuid.UUID,
    tenant_id: uuid.UUID,
    status: dict[str, Any],
) -> None:
    """Persist bounded extraction status to the file and its originating upload."""
    from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

    safe_status = safe_extraction_status(status)
    file = db.execute(
        select(DeepSpaceWorkspaceFile).where(
            DeepSpaceWorkspaceFile.id == file_id,
            DeepSpaceWorkspaceFile.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if file is not None:
        metadata = dict(file.metadata_json or {})
        metadata.pop("_extraction_attempts", None)
        metadata["extraction_status"] = safe_status
        file.metadata_json = metadata
    upload = db.execute(
        select(DeepSpaceLibraryUpload).where(
            DeepSpaceLibraryUpload.file_id == file_id,
            DeepSpaceLibraryUpload.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if upload is not None:
        metadata = dict(upload.metadata_json or {})
        metadata["extraction_status"] = safe_status
        upload.metadata_json = metadata
    db.commit()


def _enqueue_library_file_processing(
    db: Any,
    *,
    file: Any,
    tenant_id: str,
    parsed_tenant_id: uuid.UUID,
) -> None:
    """Queue optional extraction/profile work without delaying file readiness."""
    extraction = (
        file.metadata_json.get("extraction_status", {})
        if isinstance(file.metadata_json, dict)
        else {}
    )
    if safe_extraction_status(extraction, attempted=False)["state"] == "processing":
        try:
            extract_library_file.delay(file_id=str(file.id), tenant_id=tenant_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Library text extraction could not be queued", extra={"file_id": str(file.id)}
            )
            _set_library_extraction_status(
                db,
                file_id=file.id,
                tenant_id=parsed_tenant_id,
                status={
                    "state": "unavailable",
                    "text_available": bool(file.extracted_text),
                    "error_code": "EXTRACTION_QUEUE_UNAVAILABLE",
                },
            )
    metadata = file.metadata_json if isinstance(file.metadata_json, dict) else {}
    dataset_profile = metadata.get("dataset_profile", {})
    media_derivative = metadata.get("universal_derivative", {})
    if DatasetDerivativeService.supports(file.content_type):
        if not isinstance(dataset_profile, dict) or dataset_profile.get("status") != "ready":
            try:
                profile_library_dataset.delay(file_id=str(file.id), tenant_id=tenant_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Library dataset profile could not be queued", extra={"file_id": str(file.id)}
                )
    elif not isinstance(media_derivative, dict) or media_derivative.get("status") != "ready":
        try:
            profile_library_media.delay(file_id=str(file.id), tenant_id=tenant_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Library media derivative could not be queued", extra={"file_id": str(file.id)}
            )


@celery_app.task(
    bind=True,
    name="deepspace.library_file_extract",
    queue="library_extraction",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)  # type: ignore[misc]
def extract_library_file(self: Task, *, file_id: str, tenant_id: str) -> str:
    """Extract text/OCR after the private Library file is already available."""
    settings = get_settings()
    parsed_file_id = uuid.UUID(file_id)
    parsed_tenant_id = uuid.UUID(tenant_id)
    db = get_session_factory()()
    try:
        with observe_worker_stage("deepspace_library_file_extract"):
            db.execute(text("SET ROLE aks_app"))
            set_db_tenant_context(db, parsed_tenant_id)
            from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

            file = db.execute(
                select(DeepSpaceWorkspaceFile).where(
                    DeepSpaceWorkspaceFile.id == parsed_file_id,
                    DeepSpaceWorkspaceFile.tenant_id == parsed_tenant_id,
                )
            ).scalar_one_or_none()
            if file is None:
                return "not-found"
            metadata = dict(file.metadata_json or {})
            extraction_state = (metadata.get("extraction_status") or {}).get("state")
            if extraction_state != "processing":
                return str(extraction_state or "not-needed")
            attempts = int(metadata.get("_extraction_attempts", 0) or 0)
            if attempts >= 5:
                _set_library_extraction_status(
                    db,
                    file_id=parsed_file_id,
                    tenant_id=parsed_tenant_id,
                    status={
                        "state": "unavailable",
                        "text_available": bool(file.extracted_text),
                        "error_code": "EXTRACTION_WORKER_RESTARTED",
                    },
                )
                return "unavailable"
            metadata["_extraction_attempts"] = attempts + 1
            file.metadata_json = metadata
            db.commit()

            service = LibraryStorageService(settings)
            if file.is_binary:
                if not file.storage_bucket or not file.storage_key:
                    raise RuntimeError("Stored Library file has no private object reference.")
                payload = service.storage.get_bytes(
                    bucket=file.storage_bucket, object_key=file.storage_key
                )
            else:
                payload = file.content.encode("utf-8")
            extraction = service.extract(
                filename=file.name,
                content_type=file.content_type,
                payload=_bounded_extraction_payload(payload, file.content_type),
                tenant_id=parsed_tenant_id,
            )
            file.extracted_text = extraction.get("text")
            _set_library_extraction_status(
                db,
                file_id=parsed_file_id,
                tenant_id=parsed_tenant_id,
                status=extraction,
            )
            extraction_state = safe_extraction_status(extraction).get("state")
            if not isinstance(extraction_state, str):
                raise RuntimeError("Library extraction returned an invalid status.")
            return extraction_state
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if self.request.retries < self.max_retries:
            increment_worker_retry(stage="deepspace_library_file_extract")
            logger.warning(
                "Library file extraction retry scheduled",
                extra={"file_id": file_id, "retry": self.request.retries + 1},
                exc_info=True,
            )
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        increment_worker_dead_letter(stage="deepspace_library_file_extract")
        try:
            db.execute(text("SET ROLE aks_app"))
            set_db_tenant_context(db, parsed_tenant_id)
            _set_library_extraction_status(
                db,
                file_id=parsed_file_id,
                tenant_id=parsed_tenant_id,
                status={
                    "state": "unavailable",
                    "text_available": False,
                    "error_code": "EXTRACTION_FAILED",
                },
            )
        except Exception:  # noqa: BLE001
            db.rollback()
        logger.exception("Library file extraction exhausted retries", extra={"file_id": file_id})
        return "unavailable"
    finally:
        try:
            db.execute(text("RESET ROLE"))
            db.commit()
        except Exception:
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


@celery_app.task(
    bind=True,
    name="deepspace.library_media_derivative",
    queue="media_derivatives",
    max_retries=3,
)  # type: ignore[misc]
def profile_library_media(self: Task, *, file_id: str, tenant_id: str) -> str:
    """Create a bounded private manifest for non-tabular files off the API path.

    Existing OCR/document extraction remains the source of extracted text. This
    derivative adds durable format metadata, safe archive inventory, and media
    dimensions without copying decoded payloads into PostgreSQL or prompts.
    """
    settings = get_settings()
    parsed_file_id = uuid.UUID(file_id)
    parsed_tenant_id = uuid.UUID(tenant_id)
    db = get_session_factory()()
    try:
        with observe_worker_stage("deepspace_library_media_derivative"):
            db.execute(text("SET ROLE aks_app"))
            set_db_tenant_context(db, parsed_tenant_id)
            from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile

            file = db.execute(
                select(DeepSpaceWorkspaceFile).where(
                    DeepSpaceWorkspaceFile.id == parsed_file_id,
                    DeepSpaceWorkspaceFile.tenant_id == parsed_tenant_id,
                )
            ).scalar_one_or_none()
            if file is None:
                return "not-found"
            payload = (
                LibraryStorageService(settings).storage.get_bytes(
                    bucket=file.storage_bucket, object_key=file.storage_key
                )
                if file.storage_bucket and file.storage_key
                else (file.content or "").encode("utf-8")
            )
            manifest: dict[str, Any] = {
                "status": "ready",
                "source_content_type": file.content_type,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "extracted_text_available": bool(file.extracted_text),
            }
            if file.content_type == "application/zip":
                manifest["archive_entries"] = safe_archive_entries(payload)
            elif file.content_type == "application/pdf":
                try:
                    from pypdf import PdfReader

                    manifest["page_count"] = len(PdfReader(io.BytesIO(payload), strict=False).pages)
                except Exception:
                    manifest["page_count"] = None
            elif file.content_type.startswith("image/"):
                try:
                    from PIL import Image

                    with Image.open(io.BytesIO(payload)) as image:
                        manifest["width"], manifest["height"], manifest["image_format"] = (
                            image.size[0],
                            image.size[1],
                            image.format,
                        )
                except Exception:
                    manifest["image_format"] = None
            elif file.content_type.startswith(("audio/", "video/")):
                manifest["media_metadata"] = (
                    "decoder-specific metadata remains available through the media preview path"
                )
            derivative = StorageService(settings).put_bytes(
                tenant_id=parsed_tenant_id,
                document_id=uuid.uuid4(),
                filename=f"{file.name}.manifest.json",
                content_type="application/json",
                payload=json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode(
                    "utf-8"
                ),
            )
            metadata = dict(file.metadata_json or {})
            metadata["universal_derivative"] = {
                "status": "ready",
                "format": file.content_type,
                "bucket": derivative.bucket,
                "key": derivative.object_key,
                "manifest": manifest,
            }
            file.metadata_json = metadata
            db.commit()
            return "profiled"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if self.request.retries < self.max_retries:
            increment_worker_retry(stage="deepspace_library_media_derivative")
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        increment_worker_dead_letter(stage="deepspace_library_media_derivative")
        logger.exception("Library media derivative exhausted retries", extra={"file_id": file_id})
        raise
    finally:
        try:
            db.execute(text("RESET ROLE"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()
