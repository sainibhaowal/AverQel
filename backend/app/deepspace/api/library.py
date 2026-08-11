"""Tenant-scoped files visible in the DeepSpace Library drawer."""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.deepspace.models.workspace_folder import DeepSpaceWorkspaceFolder
from app.deepspace.services.library_storage import (
    LibraryStorageService,
    decode_library_payload,
    read_archive_entry,
    safe_archive_entries,
)
from app.deepspace.workers.library_uploads import finalize_library_upload
from app.platform.database.session import get_db
from app.system.services.storage_service import StorageService, StorageServiceError

router = APIRouter(prefix="/deepspace/library", tags=["deepspace-library"])
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")
_MAX_LIBRARY_CONTENT_LENGTH = 8_000_000
_LIBRARY_UPLOAD_CHUNK_SIZE = 2 * 1024 * 1024
_MAX_LIBRARY_EXPORT_FILES = 100
_MAX_LIBRARY_EXPORT_BYTES = 250 * 1024 * 1024
_LIBRARY_CONTENT_TYPES = {
    "text/css",
    "text/csv",
    "text/html",
    "text/javascript",
    "text/markdown",
    "text/plain",
    "text/sql",
    "text/x-csv",
    "text/x-diff",
    "text/x-java",
    "text/x-python",
    "text/x-yaml",
    "text/xml",
    "application/javascript",
    "application/json",
    "application/sql",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/pdf",
    "application/zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.oasis.opendocument.spreadsheet",
    "image/svg+xml",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
}
_EXTRACTABLE_LIBRARY_TYPES = {
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


def _content_type_for_name(name: str) -> str:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {
        "md": "text/markdown",
        "mdx": "text/markdown",
        "json": "application/json",
        "csv": "text/csv",
        "yaml": "application/yaml",
        "yml": "application/yaml",
        "xml": "application/xml",
        "html": "text/html",
        "htm": "text/html",
        "css": "text/css",
        "sql": "text/sql",
        "py": "text/x-python",
        "js": "text/javascript",
        "ts": "text/javascript",
        "tsx": "text/javascript",
        "diff": "text/x-diff",
        "patch": "text/x-diff",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "zip": "application/zip",
        "svg": "image/svg+xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
    }.get(extension, "text/plain")


class WorkspaceFileSchema(BaseModel):
    id: str
    name: str
    content_type: str
    source: str
    size_bytes: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    content: str | None = None
    parent_folder_id: str | None = None
    version: int = 1
    is_binary: bool = False
    checksum_sha256: str | None = None
    extracted_text: str | None = None
    download_url: str | None = None
    archive_entries: list[dict[str, object]] | None = None

    model_config = ConfigDict(extra="forbid")


class WorkspaceFileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(default="", max_length=_MAX_LIBRARY_CONTENT_LENGTH)
    content_type: str = Field(default="text/markdown", max_length=127)
    parent_folder_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_FILE_NAME.fullmatch(normalized) or normalized in {".", ".."}:
            raise ValueError(
                "File names may contain only letters, numbers, spaces, dots, underscores, and hyphens."
            )
        return normalized

    @field_validator("content_type")
    @classmethod
    def allowed_content_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _LIBRARY_CONTENT_TYPES:
            raise ValueError("This file type is not supported in the DeepSpace Library.")
        return normalized


class LibraryUploadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(default="application/octet-stream", max_length=127)
    parent_folder_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_FILE_NAME.fullmatch(normalized) or normalized in {".", ".."}:
            raise ValueError(
                "File names may contain only letters, numbers, spaces, dots, underscores, and hyphens."
            )
        return normalized

    @field_validator("content_type")
    @classmethod
    def normalized_content_type(cls, value: str) -> str:
        return value.strip().lower().split(";", 1)[0] or "application/octet-stream"


class LibraryUploadSchema(BaseModel):
    id: str
    name: str
    content_type: str
    expected_size: int
    chunk_size: int
    total_chunks: int
    received_chunks: list[int]
    bytes_received: int
    progress_percent: int
    status: str
    file_id: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class WorkspaceFileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, max_length=_MAX_LIBRARY_CONTENT_LENGTH)
    parent_folder_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return WorkspaceFileCreate.safe_name(value)


class WorkspaceFolderSchema(BaseModel):
    id: str
    name: str
    parent_folder_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class WorkspaceFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_folder_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_FILE_NAME.fullmatch(normalized) or normalized in {".", ".."}:
            raise ValueError(
                "Folder names may contain only letters, numbers, spaces, dots, underscores, and hyphens."
            )
        return normalized


class WorkspaceFolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_folder_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return WorkspaceFolderCreate.safe_name(value)


class WorkspaceFileCopy(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    parent_folder_id: str | None = None
    mode: Literal["copy", "move"] = "copy"

    model_config = ConfigDict(extra="forbid")


class LibraryExportRequest(BaseModel):
    """The selected Library files to package for an authenticated download."""

    file_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=_MAX_LIBRARY_EXPORT_FILES,
        description="One or more files owned by the current DeepSpace workspace.",
    )

    model_config = ConfigDict(extra="forbid")


def _conversation(*, db: Session, auth: AuthContext, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == auth.tenant_id,
            Conversation.user_id == auth.user_id,
            Conversation.kind == "deepspace",
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND", message="DeepSpace workspace not found", status_code=404
        )
    return conversation


def _serialize_file(
    file: DeepSpaceWorkspaceFile, *, include_content: bool = False
) -> WorkspaceFileSchema:
    content = file.content if include_content and not file.is_binary else None
    return WorkspaceFileSchema(
        id=str(file.id),
        name=file.name,
        content_type=file.content_type,
        source=file.source,
        size_bytes=file.size_bytes,
        created_at=file.created_at,
        updated_at=file.updated_at,
        content=content,
        parent_folder_id=str(file.parent_folder_id) if file.parent_folder_id else None,
        version=file.version,
        is_binary=file.is_binary,
        checksum_sha256=file.checksum_sha256,
        extracted_text=file.extracted_text if include_content else None,
        download_url=(
            f"/api/v1/deepspace/library/{file.conversation_id}/files/{file.id}/content"
            if file.is_binary
            else None
        ),
    )


def _folder_schema(folder: DeepSpaceWorkspaceFolder) -> WorkspaceFolderSchema:
    return WorkspaceFolderSchema(
        id=str(folder.id),
        name=folder.name,
        parent_folder_id=str(folder.parent_folder_id) if folder.parent_folder_id else None,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


def _owned_file(
    *, db: Session, auth: AuthContext, conversation_id: uuid.UUID, file_id: uuid.UUID
) -> DeepSpaceWorkspaceFile:
    file = db.execute(
        select(DeepSpaceWorkspaceFile).where(
            DeepSpaceWorkspaceFile.id == file_id,
            DeepSpaceWorkspaceFile.tenant_id == auth.tenant_id,
            DeepSpaceWorkspaceFile.user_id == auth.user_id,
            DeepSpaceWorkspaceFile.conversation_id == conversation_id,
        )
    ).scalar_one_or_none()
    if file is None:
        raise ApiError(code="NOT_FOUND", message="DeepSpace file not found", status_code=404)
    return file


def _owned_folder(
    *, db: Session, auth: AuthContext, conversation_id: uuid.UUID, folder_id: uuid.UUID
) -> DeepSpaceWorkspaceFolder:
    folder = db.execute(
        select(DeepSpaceWorkspaceFolder).where(
            DeepSpaceWorkspaceFolder.id == folder_id,
            DeepSpaceWorkspaceFolder.tenant_id == auth.tenant_id,
            DeepSpaceWorkspaceFolder.user_id == auth.user_id,
            DeepSpaceWorkspaceFolder.conversation_id == conversation_id,
        )
    ).scalar_one_or_none()
    if folder is None:
        raise ApiError(code="NOT_FOUND", message="DeepSpace folder not found", status_code=404)
    return folder


def _library_file_payload(*, file: DeepSpaceWorkspaceFile, settings: Settings) -> bytes:
    """Read a file's original bytes without exposing object-storage URLs."""
    if not file.is_binary:
        return (file.content or "").encode("utf-8")
    if not file.storage_bucket or not file.storage_key:
        raise ApiError(
            code="STORAGE_OBJECT_NOT_FOUND",
            message="Library file payload is missing.",
            status_code=404,
        )
    try:
        return StorageService(settings).get_bytes(
            bucket=file.storage_bucket, object_key=file.storage_key
        )
    except StorageServiceError as exc:
        raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc


def _library_folder_path(
    file: DeepSpaceWorkspaceFile,
    folders: dict[uuid.UUID, DeepSpaceWorkspaceFolder],
) -> str:
    """Build a safe relative ZIP path from the Library folder hierarchy."""
    parts: list[str] = [file.name]
    current = file.parent_folder_id
    visited: set[uuid.UUID] = set()
    while current is not None and current not in visited and len(parts) < 256:
        visited.add(current)
        folder = folders.get(current)
        if folder is None:
            break
        parts.append(folder.name)
        current = folder.parent_folder_id
    path = posixpath.normpath("/".join(reversed(parts)))
    if path.startswith("/") or path == "." or path == ".." or path.startswith("../"):
        return file.name
    return path


def _parse_optional_uuid(value: str | None, label: str) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError(
            code="INVALID_REQUEST", message=f"Invalid {label}.", status_code=422
        ) from exc


def _add_version(db: Session, file: DeepSpaceWorkspaceFile) -> None:
    db.add(
        DeepSpaceWorkspaceFileVersion(
            file_id=file.id,
            tenant_id=file.tenant_id,
            user_id=file.user_id,
            conversation_id=file.conversation_id,
            version=file.version,
            name=file.name,
            content_type=file.content_type,
            content=file.content if not file.is_binary else None,
            storage_bucket=file.storage_bucket,
            storage_key=file.storage_key,
            checksum_sha256=file.checksum_sha256 or hashlib.sha256(b"").hexdigest(),
            size_bytes=file.size_bytes,
            metadata_json={"is_binary": file.is_binary},
        )
    )


def _serialize_upload(upload: DeepSpaceLibraryUpload) -> LibraryUploadSchema:
    return LibraryUploadSchema(
        id=str(upload.id),
        name=upload.filename,
        content_type=upload.content_type,
        expected_size=upload.expected_size,
        chunk_size=upload.chunk_size,
        total_chunks=upload.total_chunks,
        received_chunks=sorted(int(index) for index in (upload.received_chunks or [])),
        bytes_received=upload.bytes_received,
        progress_percent=(
            min(100, int(upload.bytes_received * 100 / upload.expected_size))
            if upload.expected_size
            else 0
        ),
        status=upload.status,
        file_id=str(upload.file_id) if upload.file_id else None,
        error=upload.error_message,
        created_at=upload.created_at,
        updated_at=upload.updated_at,
    )


def _owned_upload(
    *, db: Session, auth: AuthContext, conversation_id: uuid.UUID, upload_id: uuid.UUID
) -> DeepSpaceLibraryUpload:
    upload = db.execute(
        select(DeepSpaceLibraryUpload).where(
            DeepSpaceLibraryUpload.id == upload_id,
            DeepSpaceLibraryUpload.tenant_id == auth.tenant_id,
            DeepSpaceLibraryUpload.user_id == auth.user_id,
            DeepSpaceLibraryUpload.conversation_id == conversation_id,
        )
    ).scalar_one_or_none()
    if upload is None:
        raise ApiError(code="NOT_FOUND", message="Library upload not found.", status_code=404)
    return upload


@router.post(
    "/{conversation_id}/uploads",
    response_model=LibraryUploadSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def create_library_upload(
    conversation_id: uuid.UUID,
    payload: LibraryUploadCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LibraryUploadSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    if payload.size_bytes > settings.upload_max_bytes:
        raise ApiError(
            code="DOC_TOO_LARGE",
            message="The file exceeds the configured upload limit.",
            status_code=413,
        )
    parent_id = _parse_optional_uuid(payload.parent_folder_id, "parent_folder_id")
    if parent_id:
        _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
    duplicate_query = select(DeepSpaceWorkspaceFile.id).where(
        DeepSpaceWorkspaceFile.tenant_id == auth.tenant_id,
        DeepSpaceWorkspaceFile.user_id == auth.user_id,
        DeepSpaceWorkspaceFile.conversation_id == conversation_id,
        DeepSpaceWorkspaceFile.name == payload.name,
    )
    duplicate_query = duplicate_query.where(
        DeepSpaceWorkspaceFile.parent_folder_id.is_(None)
        if parent_id is None
        else DeepSpaceWorkspaceFile.parent_folder_id == parent_id
    )
    if db.execute(duplicate_query).scalar_one_or_none() is not None:
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A file with that name already exists in this workspace.",
            status_code=409,
        )
    content_type = payload.content_type
    if content_type not in _LIBRARY_CONTENT_TYPES:
        content_type = _content_type_for_name(payload.name)
    if content_type not in _LIBRARY_CONTENT_TYPES:
        raise ApiError(
            code="INVALID_UPLOAD_TYPE",
            message="This file type is not supported in the DeepSpace Library.",
            status_code=422,
        )
    total_chunks = (
        payload.size_bytes + _LIBRARY_UPLOAD_CHUNK_SIZE - 1
    ) // _LIBRARY_UPLOAD_CHUNK_SIZE
    upload = DeepSpaceLibraryUpload(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        parent_folder_id=parent_id,
        filename=payload.name,
        content_type=content_type,
        expected_size=payload.size_bytes,
        chunk_size=_LIBRARY_UPLOAD_CHUNK_SIZE,
        total_chunks=total_chunks,
        received_chunks=[],
        bytes_received=0,
        status="pending",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return _serialize_upload(upload)


@router.get(
    "/{conversation_id}/uploads",
    response_model=list[LibraryUploadSchema],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_library_uploads(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[LibraryUploadSchema]:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    uploads = db.execute(
        select(DeepSpaceLibraryUpload)
        .where(
            DeepSpaceLibraryUpload.tenant_id == auth.tenant_id,
            DeepSpaceLibraryUpload.user_id == auth.user_id,
            DeepSpaceLibraryUpload.conversation_id == conversation_id,
            DeepSpaceLibraryUpload.status.in_(
                ["pending", "uploading", "queued", "processing", "failed"]
            ),
        )
        .order_by(DeepSpaceLibraryUpload.created_at.desc())
        .limit(50)
    ).scalars()
    return [_serialize_upload(upload) for upload in uploads]


@router.get(
    "/{conversation_id}/uploads/{upload_id}",
    response_model=LibraryUploadSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_library_upload(
    conversation_id: uuid.UUID,
    upload_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LibraryUploadSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    return _serialize_upload(
        _owned_upload(db=db, auth=auth, conversation_id=conversation_id, upload_id=upload_id)
    )


@router.put(
    "/{conversation_id}/uploads/{upload_id}/chunks/{chunk_index}",
    response_model=LibraryUploadSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def upload_library_chunk(
    conversation_id: uuid.UUID,
    upload_id: uuid.UUID,
    chunk_index: int,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LibraryUploadSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    upload = _owned_upload(db=db, auth=auth, conversation_id=conversation_id, upload_id=upload_id)
    if upload.status in {"cancelled", "completed", "processing", "failed"}:
        raise ApiError(
            code="UPLOAD_NOT_ACTIVE",
            message="This upload is no longer accepting chunks.",
            status_code=409,
        )
    if chunk_index < 0 or chunk_index >= upload.total_chunks:
        raise ApiError(
            code="INVALID_CHUNK", message="The upload chunk number is invalid.", status_code=422
        )
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > upload.chunk_size:
                raise ApiError(
                    code="INVALID_CHUNK", message="The upload chunk is too large.", status_code=413
                )
        except ValueError:
            raise ApiError(
                code="INVALID_CHUNK", message="The upload chunk length is invalid.", status_code=422
            ) from None
    body_parts: list[bytes] = []
    body_size = 0
    async for part in request.stream():
        body_size += len(part)
        if body_size > upload.chunk_size:
            raise ApiError(
                code="INVALID_CHUNK", message="The upload chunk is too large.", status_code=413
            )
        body_parts.append(part)
    body = b"".join(body_parts)
    expected_length = min(upload.chunk_size, upload.expected_size - chunk_index * upload.chunk_size)
    if len(body) != expected_length or len(body) > upload.chunk_size:
        raise ApiError(
            code="INVALID_CHUNK", message="The upload chunk size is invalid.", status_code=422
        )
    try:
        StorageService(settings).put_upload_chunk(
            tenant_id=auth.tenant_id,
            upload_id=upload.id,
            chunk_index=chunk_index,
            payload=body,
        )
    except StorageServiceError as exc:
        raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc
    received = {int(index) for index in (upload.received_chunks or [])}
    received.add(chunk_index)
    upload.received_chunks = sorted(received)
    upload.bytes_received = sum(
        min(upload.chunk_size, upload.expected_size - index * upload.chunk_size)
        for index in received
    )
    upload.status = "uploading"
    upload.error_message = None
    db.commit()
    db.refresh(upload)
    return _serialize_upload(upload)


@router.post(
    "/{conversation_id}/uploads/{upload_id}/complete",
    response_model=LibraryUploadSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def complete_library_upload(
    conversation_id: uuid.UUID,
    upload_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> LibraryUploadSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    upload = _owned_upload(db=db, auth=auth, conversation_id=conversation_id, upload_id=upload_id)
    if upload.status == "completed":
        return _serialize_upload(upload)
    if upload.status == "cancelled":
        raise ApiError(
            code="UPLOAD_CANCELLED", message="This upload was cancelled.", status_code=409
        )
    if (
        len(upload.received_chunks or []) != upload.total_chunks
        or upload.bytes_received != upload.expected_size
    ):
        raise ApiError(
            code="UPLOAD_INCOMPLETE",
            message="Some upload chunks are still missing.",
            status_code=409,
        )
    upload.status = "queued"
    db.commit()
    try:
        finalize_library_upload.delay(upload_id=str(upload.id), tenant_id=str(auth.tenant_id))
    except Exception as exc:  # noqa: BLE001
        upload.status = "failed"
        upload.error_message = "The Library upload worker could not be started."
        db.commit()
        raise ApiError(
            code="UPLOAD_QUEUE_UNAVAILABLE", message=upload.error_message, status_code=503
        ) from exc
    db.refresh(upload)
    return _serialize_upload(upload)


@router.post(
    "/{conversation_id}/uploads/{upload_id}/cancel",
    response_model=LibraryUploadSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def cancel_library_upload(
    conversation_id: uuid.UUID,
    upload_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LibraryUploadSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    upload = _owned_upload(db=db, auth=auth, conversation_id=conversation_id, upload_id=upload_id)
    if upload.status not in {"completed", "cancelled"}:
        upload.status = "cancelled"
        upload.error_message = "Upload cancelled by the user."
        db.commit()
        StorageService(settings).delete_upload_chunks(
            tenant_id=auth.tenant_id, upload_id=upload.id, total_chunks=upload.total_chunks
        )
        db.refresh(upload)
    return _serialize_upload(upload)


@router.get(
    "/{conversation_id}/files",
    response_model=list[WorkspaceFileSchema],
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_workspace_files(
    conversation_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[WorkspaceFileSchema]:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    files = (
        db.execute(
            select(DeepSpaceWorkspaceFile)
            .where(
                DeepSpaceWorkspaceFile.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFile.user_id == auth.user_id,
                DeepSpaceWorkspaceFile.conversation_id == conversation_id,
            )
            .order_by(
                DeepSpaceWorkspaceFile.updated_at.desc(), DeepSpaceWorkspaceFile.created_at.desc()
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_file(file) for file in files]


@router.get(
    "/{conversation_id}/entries",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_workspace_entries(
    conversation_id: uuid.UUID,
    parent_folder_id: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return one explorer page: folders first, then files in that folder."""
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    parent_id = _parse_optional_uuid(parent_folder_id, "parent_folder_id")
    if parent_id:
        _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
    folders = (
        db.execute(
            select(DeepSpaceWorkspaceFolder)
            .where(
                DeepSpaceWorkspaceFolder.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFolder.user_id == auth.user_id,
                DeepSpaceWorkspaceFolder.conversation_id == conversation_id,
                DeepSpaceWorkspaceFolder.parent_folder_id == parent_id,
            )
            .order_by(DeepSpaceWorkspaceFolder.name.asc())
        )
        .scalars()
        .all()
    )
    files = (
        db.execute(
            select(DeepSpaceWorkspaceFile)
            .where(
                DeepSpaceWorkspaceFile.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFile.user_id == auth.user_id,
                DeepSpaceWorkspaceFile.conversation_id == conversation_id,
                DeepSpaceWorkspaceFile.parent_folder_id == parent_id,
            )
            .order_by(DeepSpaceWorkspaceFile.name.asc())
        )
        .scalars()
        .all()
    )
    return {
        "parent_folder_id": str(parent_id) if parent_id else None,
        "folders": [_folder_schema(folder).model_dump(mode="json") for folder in folders],
        "files": [_serialize_file(file).model_dump(mode="json") for file in files],
    }


@router.post(
    "/{conversation_id}/folders",
    response_model=WorkspaceFolderSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def create_workspace_folder(
    conversation_id: uuid.UUID,
    payload: WorkspaceFolderCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WorkspaceFolderSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    parent_id = _parse_optional_uuid(payload.parent_folder_id, "parent_folder_id")
    if parent_id:
        _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
    folder = DeepSpaceWorkspaceFolder(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        parent_folder_id=parent_id,
        name=payload.name,
    )
    db.add(folder)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A folder with that name already exists here.",
            status_code=409,
        ) from exc
    db.refresh(folder)
    return _folder_schema(folder)


@router.patch(
    "/{conversation_id}/folders/{folder_id}",
    response_model=WorkspaceFolderSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def update_workspace_folder(
    conversation_id: uuid.UUID,
    folder_id: uuid.UUID,
    payload: WorkspaceFolderUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WorkspaceFolderSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    folder = _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=folder_id)
    parent_id = _parse_optional_uuid(payload.parent_folder_id, "parent_folder_id")
    if parent_id:
        parent = _owned_folder(
            db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id
        )
        if parent.id == folder.id:
            raise ApiError(
                code="INVALID_REQUEST", message="A folder cannot contain itself.", status_code=422
            )
        # Prevent moving a folder into one of its descendants.
        cursor = parent
        while cursor.parent_folder_id:
            if cursor.parent_folder_id == folder.id:
                raise ApiError(
                    code="INVALID_REQUEST",
                    message="A folder cannot move into its descendant.",
                    status_code=422,
                )
            cursor = _owned_folder(
                db=db, auth=auth, conversation_id=conversation_id, folder_id=cursor.parent_folder_id
            )
    if payload.name is not None:
        folder.name = payload.name
    folder.parent_folder_id = parent_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A folder with that name already exists here.",
            status_code=409,
        ) from exc
    db.refresh(folder)
    return _folder_schema(folder)


@router.delete(
    "/{conversation_id}/folders/{folder_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def delete_workspace_folder(
    conversation_id: uuid.UUID,
    folder_id: uuid.UUID,
    recursive: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    folder = _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=folder_id)
    child_count = (
        db.scalar(
            select(sa_func.count())
            .select_from(DeepSpaceWorkspaceFolder)
            .where(DeepSpaceWorkspaceFolder.parent_folder_id == folder.id)
        )
        or 0
    )
    file_count = (
        db.scalar(
            select(sa_func.count())
            .select_from(DeepSpaceWorkspaceFile)
            .where(DeepSpaceWorkspaceFile.parent_folder_id == folder.id)
        )
        or 0
    )
    if (child_count or file_count) and not recursive:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Folder is not empty. Confirm recursive deletion.",
            status_code=409,
        )
    if recursive:
        # Collect the complete subtree before the database cascade so private
        # MinIO objects are removed together with their metadata rows.
        folder_rows = db.execute(
            select(DeepSpaceWorkspaceFolder.id, DeepSpaceWorkspaceFolder.parent_folder_id).where(
                DeepSpaceWorkspaceFolder.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFolder.user_id == auth.user_id,
                DeepSpaceWorkspaceFolder.conversation_id == conversation_id,
            )
        ).all()
        children: dict[uuid.UUID, list[uuid.UUID]] = {}
        for child_id, parent_id in folder_rows:
            if parent_id is not None:
                children.setdefault(parent_id, []).append(child_id)
        subtree: set[uuid.UUID] = {folder.id}
        pending = [folder.id]
        while pending:
            current = pending.pop()
            for child_id in children.get(current, []):
                if child_id not in subtree:
                    subtree.add(child_id)
                    pending.append(child_id)
        files = (
            db.execute(
                select(DeepSpaceWorkspaceFile).where(
                    DeepSpaceWorkspaceFile.tenant_id == auth.tenant_id,
                    DeepSpaceWorkspaceFile.user_id == auth.user_id,
                    DeepSpaceWorkspaceFile.conversation_id == conversation_id,
                    DeepSpaceWorkspaceFile.parent_folder_id.in_(subtree),
                )
            )
            .scalars()
            .all()
        )
        storage = StorageService(settings)
        for item in files:
            if item.storage_bucket and item.storage_key:
                storage.delete_object(bucket=item.storage_bucket, object_key=item.storage_key)
    db.delete(folder)
    db.commit()


@router.post(
    "/{conversation_id}/files/export",
    response_model=None,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def export_workspace_files(
    conversation_id: uuid.UUID,
    payload: LibraryExportRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Package selected Library files into a private, authenticated ZIP download."""
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    requested_ids = list(dict.fromkeys(payload.file_ids))
    if len(requested_ids) != len(payload.file_ids):
        raise ApiError(
            code="INVALID_REQUEST", message="A file may only be selected once.", status_code=422
        )
    files = (
        db.execute(
            select(DeepSpaceWorkspaceFile).where(
                DeepSpaceWorkspaceFile.id.in_(requested_ids),
                DeepSpaceWorkspaceFile.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFile.user_id == auth.user_id,
                DeepSpaceWorkspaceFile.conversation_id == conversation_id,
            )
        )
        .scalars()
        .all()
    )
    if len(files) != len(requested_ids):
        raise ApiError(
            code="NOT_FOUND",
            message="One or more selected Library files were not found.",
            status_code=404,
        )
    total_size = sum(max(0, file.size_bytes) for file in files)
    if total_size > _MAX_LIBRARY_EXPORT_BYTES:
        raise ApiError(
            code="EXPORT_TOO_LARGE",
            message="The selected files exceed the safe export size limit.",
            status_code=413,
        )
    folder_rows = (
        db.execute(
            select(DeepSpaceWorkspaceFolder).where(
                DeepSpaceWorkspaceFolder.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFolder.user_id == auth.user_id,
                DeepSpaceWorkspaceFolder.conversation_id == conversation_id,
            )
        )
        .scalars()
        .all()
    )
    folders = {folder.id: folder for folder in folder_rows}
    archive = io.BytesIO()
    used_names: set[str] = set()
    exported_bytes = 0
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as output:
        # Keep the user's selection order, rather than database ordering.
        files_by_id = {file.id: file for file in files}
        for file_id in requested_ids:
            file = files_by_id[file_id]
            entry_name = _library_folder_path(file, folders)
            if entry_name in used_names:
                stem, dot, suffix = entry_name.rpartition(".")
                base = stem if dot else entry_name
                extension = f".{suffix}" if dot else ""
                index = 2
                candidate = f"{base} ({index}){extension}"
                while candidate in used_names:
                    index += 1
                    candidate = f"{base} ({index}){extension}"
                entry_name = candidate
            used_names.add(entry_name)
            file_payload = _library_file_payload(file=file, settings=settings)
            exported_bytes += len(file_payload)
            if exported_bytes > _MAX_LIBRARY_EXPORT_BYTES:
                raise ApiError(
                    code="EXPORT_TOO_LARGE",
                    message="The selected files exceed the safe export size limit.",
                    status_code=413,
                )
            output.writestr(entry_name, file_payload)
    payload_bytes = archive.getvalue()
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Length": str(len(payload_bytes)),
        "Content-Disposition": "attachment; filename=deepspace-library-export.zip",
    }
    return StreamingResponse(iter([payload_bytes]), media_type="application/zip", headers=headers)


@router.get(
    "/{conversation_id}/files/{file_id}",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_workspace_file(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    result = _serialize_file(file, include_content=True)
    if file.is_binary and file.storage_bucket and file.storage_key:
        try:
            if file.content_type == "application/zip":
                payload = StorageService(settings).get_bytes(
                    bucket=file.storage_bucket, object_key=file.storage_key
                )
                result.archive_entries = safe_archive_entries(payload)
        except StorageServiceError as exc:
            raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc
    return result


@router.post(
    "/{conversation_id}/files",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def create_workspace_file(
    conversation_id: uuid.UUID,
    payload: WorkspaceFileCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    parent_id = _parse_optional_uuid(payload.parent_folder_id, "parent_folder_id")
    if parent_id:
        _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
    decoded = decode_library_payload(payload.content, payload.content_type)
    if decoded.content_type not in _LIBRARY_CONTENT_TYPES:
        raise ApiError(
            code="INVALID_UPLOAD_TYPE",
            message="This file type is not supported in the DeepSpace Library.",
            status_code=422,
        )
    if len(decoded.payload) > settings.upload_max_bytes:
        raise ApiError(
            code="DOC_TOO_LARGE",
            message="The file exceeds the configured upload limit.",
            status_code=413,
        )
    file_id = uuid.uuid4()
    is_binary = decoded.is_binary or not decoded.content_type.startswith(
        ("text/", "application/json", "application/xml", "application/yaml")
    )
    extraction = (
        LibraryStorageService(settings).extract(
            filename=payload.name,
            content_type=decoded.content_type,
            payload=decoded.payload,
            tenant_id=auth.tenant_id,
        )
        if decoded.content_type in _EXTRACTABLE_LIBRARY_TYPES
        else {"text": None}
    )
    file = DeepSpaceWorkspaceFile(
        id=file_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        parent_folder_id=parent_id,
        name=payload.name,
        content_type=decoded.content_type,
        content="" if is_binary else payload.content,
        size_bytes=len(decoded.payload),
        source="user",
        checksum_sha256=LibraryStorageService.checksum(decoded.payload),
        extracted_text=extraction.get("text"),
        is_binary=is_binary,
    )
    stored = None
    if is_binary:
        stored = LibraryStorageService(settings).store(
            tenant_id=auth.tenant_id,
            file_id=file_id,
            filename=payload.name,
            content_type=decoded.content_type,
            payload=decoded.payload,
        )
        file.storage_bucket = stored.bucket
        file.storage_key = stored.object_key
    db.add(file)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if stored is not None:
            StorageService(settings).delete_object(
                bucket=stored.bucket, object_key=stored.object_key
            )
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A file with that name already exists in this workspace",
            status_code=409,
        ) from exc
    _add_version(db, file)
    db.commit()
    db.refresh(file)
    return _serialize_file(file, include_content=True)


@router.patch(
    "/{conversation_id}/files/{file_id}",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def update_workspace_file(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: WorkspaceFileUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    if payload.expected_version is not None and payload.expected_version != file.version:
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="The file changed since it was opened. Reload before saving.",
            status_code=409,
        )
    parent_was_provided = "parent_folder_id" in payload.model_fields_set
    changed = payload.name is not None or payload.content is not None or parent_was_provided
    if payload.name is not None:
        file.name = payload.name
        if not file.is_binary:
            file.content_type = _content_type_for_name(payload.name)
    if parent_was_provided:
        parent_id = _parse_optional_uuid(payload.parent_folder_id, "parent_folder_id")
        if parent_id:
            _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
        file.parent_folder_id = parent_id
    if payload.content is not None:
        if file.is_binary:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Binary files must be replaced through file upload.",
                status_code=422,
            )
        file.content = payload.content
        file.size_bytes = len(payload.content.encode("utf-8"))
        file.checksum_sha256 = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    if changed:
        file.version += 1
        file.updated_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A file with that name already exists in this workspace",
            status_code=409,
        ) from exc
    _add_version(db, file)
    db.commit()
    db.refresh(file)
    return _serialize_file(file, include_content=True)


@router.post(
    "/{conversation_id}/files/upload",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def upload_workspace_file(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),  # noqa: B008
    parent_folder_id: str | None = Query(default=None),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    name = (file.filename or "upload.bin").strip()
    try:
        name = WorkspaceFileCreate.safe_name(name)
    except ValueError as exc:
        raise ApiError(code="INVALID_UPLOAD_FILENAME", message=str(exc), status_code=422) from exc
    parent_id = _parse_optional_uuid(parent_folder_id, "parent_folder_id")
    if parent_id:
        _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
    payload = await file.read(settings.upload_max_bytes + 1)
    if len(payload) > settings.upload_max_bytes:
        raise ApiError(
            code="DOC_TOO_LARGE",
            message="The file exceeds the configured upload limit.",
            status_code=413,
        )
    content_type = (file.content_type or _content_type_for_name(name)).lower().split(";", 1)[0]
    if content_type not in _LIBRARY_CONTENT_TYPES:
        content_type = _content_type_for_name(name)
    file_id = uuid.uuid4()
    is_binary = not content_type.startswith(
        ("text/", "application/json", "application/xml", "application/yaml")
    )
    extraction = (
        LibraryStorageService(settings).extract(
            filename=name, content_type=content_type, payload=payload, tenant_id=auth.tenant_id
        )
        if content_type in _EXTRACTABLE_LIBRARY_TYPES
        else {"text": None}
    )
    record = DeepSpaceWorkspaceFile(
        id=file_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        parent_folder_id=parent_id,
        name=name,
        content_type=content_type,
        content="" if is_binary else payload.decode("utf-8", errors="replace"),
        source="user",
        size_bytes=len(payload),
        checksum_sha256=LibraryStorageService.checksum(payload),
        extracted_text=extraction.get("text"),
        is_binary=is_binary,
    )
    stored = None
    if is_binary:
        stored = LibraryStorageService(settings).store(
            tenant_id=auth.tenant_id,
            file_id=file_id,
            filename=name,
            content_type=content_type,
            payload=payload,
        )
        record.storage_bucket, record.storage_key = stored.bucket, stored.object_key
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if stored is not None:
            StorageService(settings).delete_object(
                bucket=stored.bucket, object_key=stored.object_key
            )
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A file with that name already exists in this workspace.",
            status_code=409,
        ) from exc
    _add_version(db, record)
    db.commit()
    db.refresh(record)
    return _serialize_file(record, include_content=True)


@router.post(
    "/{conversation_id}/files/{file_id}/copy",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def copy_workspace_file(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: WorkspaceFileCopy,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    source = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    name = WorkspaceFileCreate.safe_name(
        payload.name or f"{source.name.rsplit('.', 1)[0]} copy.{source.name.rsplit('.', 1)[1]}"
        if "." in source.name
        else f"{source.name} copy"
    )
    parent_id = _parse_optional_uuid(payload.parent_folder_id, "parent_folder_id")
    if parent_id:
        _owned_folder(db=db, auth=auth, conversation_id=conversation_id, folder_id=parent_id)
    if payload.mode == "move":
        if payload.name is not None:
            source.name = WorkspaceFileCreate.safe_name(payload.name)
        source.parent_folder_id = parent_id
        source.version += 1
        source.updated_at = datetime.now(UTC)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ApiError(
                code="IDEMPOTENCY_CONFLICT",
                message="A file with that name already exists in this folder.",
                status_code=409,
            ) from exc
        _add_version(db, source)
        db.commit()
        db.refresh(source)
        return _serialize_file(source, include_content=True)
    clone = DeepSpaceWorkspaceFile(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        parent_folder_id=parent_id,
        name=name,
        content_type=source.content_type,
        content=source.content,
        source="user",
        size_bytes=source.size_bytes,
        storage_bucket=source.storage_bucket,
        storage_key=source.storage_key,
        checksum_sha256=source.checksum_sha256,
        extracted_text=source.extracted_text,
        is_binary=source.is_binary,
    )
    stored = None
    if source.is_binary and source.storage_bucket and source.storage_key:
        db.add(clone)
        db.flush()
        stored = StorageService(settings).copy_object(
            bucket=source.storage_bucket,
            source_key=source.storage_key,
            tenant_id=auth.tenant_id,
            document_id=clone.id,
            filename=clone.name,
            content_type=clone.content_type,
        )
        clone.storage_bucket, clone.storage_key = stored.bucket, stored.object_key
        clone.metadata_json = {**(source.metadata_json or {}), "copied_from": str(source.id)}
    else:
        db.add(clone)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if stored is not None:
            StorageService(settings).delete_object(
                bucket=stored.bucket, object_key=stored.object_key
            )
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="A file with that name already exists in this workspace.",
            status_code=409,
        ) from exc
    _add_version(db, clone)
    db.commit()
    db.refresh(clone)
    return _serialize_file(clone, include_content=True)


@router.get(
    "/{conversation_id}/files/{file_id}/versions",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def list_workspace_file_versions(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    versions = (
        db.execute(
            select(DeepSpaceWorkspaceFileVersion)
            .where(
                DeepSpaceWorkspaceFileVersion.file_id == file_id,
                DeepSpaceWorkspaceFileVersion.tenant_id == auth.tenant_id,
                DeepSpaceWorkspaceFileVersion.user_id == auth.user_id,
            )
            .order_by(DeepSpaceWorkspaceFileVersion.version.desc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(item.id),
            "version": item.version,
            "name": item.name,
            "content_type": item.content_type,
            "size_bytes": item.size_bytes,
            "checksum_sha256": item.checksum_sha256,
            "created_at": item.created_at,
        }
        for item in versions
    ]


@router.post(
    "/{conversation_id}/files/{file_id}/versions/{version}/restore",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def restore_workspace_file_version(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    version: int,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    snapshot = db.execute(
        select(DeepSpaceWorkspaceFileVersion).where(
            DeepSpaceWorkspaceFileVersion.file_id == file.id,
            DeepSpaceWorkspaceFileVersion.version == version,
            DeepSpaceWorkspaceFileVersion.tenant_id == auth.tenant_id,
            DeepSpaceWorkspaceFileVersion.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise ApiError(code="NOT_FOUND", message="Library file version not found", status_code=404)
    # SQLAlchemy's class-level Column typing is not precise for ORM instances.
    restored_file = cast(Any, file)
    restored_file.name = snapshot.name
    restored_file.content_type = snapshot.content_type
    restored_file.content = snapshot.content
    restored_file.storage_bucket = snapshot.storage_bucket
    restored_file.storage_key = snapshot.storage_key
    restored_file.checksum_sha256 = snapshot.checksum_sha256
    restored_file.size_bytes = snapshot.size_bytes
    restored_file.is_binary = snapshot.content is None
    file.version += 1
    file.updated_at = datetime.now(UTC)
    _add_version(db, file)
    db.commit()
    db.refresh(file)
    return _serialize_file(file, include_content=True)


@router.get(
    "/{conversation_id}/files/{file_id}/content",
    response_model=None,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def stream_workspace_file_content(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    download: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse | PlainTextResponse:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    disposition = "attachment" if download else "inline"
    safe_name = quote(file.name, safe="._-")
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Disposition": f"{disposition}; filename=\"{file.name}\"; filename*=UTF-8''{safe_name}",
    }
    payload = _library_file_payload(file=file, settings=settings)
    if not file.is_binary:
        return PlainTextResponse(
            payload.decode("utf-8", errors="replace"), media_type=file.content_type, headers=headers
        )
    headers["Content-Length"] = str(len(payload))
    return StreamingResponse(iter([payload]), media_type=file.content_type, headers=headers)


@router.get(
    "/{conversation_id}/files/{file_id}/archive/{entry_name:path}",
    response_model=None,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def read_workspace_archive_entry(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    entry_name: str,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse | PlainTextResponse:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    if file.content_type != "application/zip" or not file.storage_bucket or not file.storage_key:
        raise ApiError(
            code="INVALID_REQUEST",
            message="The selected Library file is not a ZIP archive.",
            status_code=422,
        )
    try:
        archive = StorageService(settings).get_bytes(
            bucket=file.storage_bucket, object_key=file.storage_key
        )
        payload = read_archive_entry(archive, entry_name)
    except StorageServiceError as exc:
        raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc
    content_type = _content_type_for_name(entry_name)
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
    if content_type.startswith(
        ("text/", "application/json", "application/xml", "application/yaml")
    ):
        return PlainTextResponse(
            payload.decode("utf-8", errors="replace"), media_type=content_type, headers=headers
        )
    headers["Content-Length"] = str(len(payload))
    return StreamingResponse(iter([payload]), media_type=content_type, headers=headers)


@router.delete(
    "/{conversation_id}/files/{file_id}",
    status_code=204,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def delete_workspace_file(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    if file.storage_bucket and file.storage_key:
        StorageService(settings).delete_object(
            bucket=file.storage_bucket, object_key=file.storage_key
        )
    db.delete(file)
    db.commit()
