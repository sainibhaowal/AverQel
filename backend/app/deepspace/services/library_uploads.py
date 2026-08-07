"""Shared durable Library upload finalization logic."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.deepspace.services.library_storage import LibraryStorageService


def finalize_upload(
    db: Session,
    *,
    settings: Settings,
    upload: DeepSpaceLibraryUpload,
    payload: bytes,
) -> DeepSpaceWorkspaceFile:
    """Create the normal Library file from a verified assembled upload payload."""
    if len(payload) != upload.expected_size:
        raise ApiError(
            code="UPLOAD_SIZE_MISMATCH",
            message="The uploaded file size does not match its upload session.",
            status_code=422,
        )
    content_type = upload.content_type
    is_binary = not content_type.startswith(
        ("text/", "application/json", "application/xml", "application/yaml")
    )
    storage_service = LibraryStorageService(settings)
    extraction = (
        storage_service.extract(
            filename=upload.filename,
            content_type=content_type,
            payload=payload,
            tenant_id=upload.tenant_id,
        )
        if content_type
        in {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
            "text/csv",
            "text/plain",
            "text/markdown",
            "application/json",
            "application/xml",
            "application/yaml",
        }
        else {"text": None}
    )
    file_id = uuid.uuid4()
    record = DeepSpaceWorkspaceFile(
        id=file_id,
        tenant_id=upload.tenant_id,
        user_id=upload.user_id,
        conversation_id=upload.conversation_id,
        parent_folder_id=upload.parent_folder_id,
        name=upload.filename,
        content_type=content_type,
        content="" if is_binary else payload.decode("utf-8", errors="replace"),
        source="user",
        size_bytes=len(payload),
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
        extracted_text=extraction.get("text"),
        is_binary=is_binary,
    )
    stored = None
    if is_binary:
        stored = storage_service.store(
            tenant_id=upload.tenant_id,
            file_id=file_id,
            filename=upload.filename,
            content_type=content_type,
            payload=payload,
        )
        record.storage_bucket = stored.bucket
        record.storage_key = stored.object_key
    try:
        db.add(record)
        db.flush()
        db.add(
            DeepSpaceWorkspaceFileVersion(
                file_id=record.id,
                tenant_id=record.tenant_id,
                user_id=record.user_id,
                conversation_id=record.conversation_id,
                version=record.version,
                name=record.name,
                content_type=record.content_type,
                content=record.content if not record.is_binary else None,
                storage_bucket=record.storage_bucket,
                storage_key=record.storage_key,
                checksum_sha256=record.checksum_sha256 or hashlib.sha256(b"").hexdigest(),
                size_bytes=record.size_bytes,
                metadata_json={"is_binary": record.is_binary},
            )
        )
        db.flush()
    except Exception:
        if stored is not None:
            stored_service = storage_service.storage
            stored_service.delete_object(bucket=stored.bucket, object_key=stored.object_key)
        raise
    return record
