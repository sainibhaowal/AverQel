"""Tenant-scoped files visible in the DeepSpace Library drawer."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import posixpath
import re
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.deepspace.integrations.export_service import DeepSpaceExportService
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.deepspace.models.workspace_folder import DeepSpaceWorkspaceFolder
from app.deepspace.services.dataset_derivatives import DatasetDerivativeService
from app.deepspace.services.library_storage import (
    LibraryStorageService,
    decode_library_payload,
    read_archive_entry,
    safe_archive_entries,
)
from app.deepspace.workers.library_uploads import finalize_library_upload, profile_library_dataset
from app.ingestion.services.office_writer import text_to_docx, text_to_pptx, text_to_xlsx
from app.platform.database.session import get_db
from app.system.services.storage_service import StorageService, StorageServiceError

router = APIRouter(prefix="/deepspace/library", tags=["deepspace-library"])
# Keep names safe for object-storage keys while allowing normal Unicode names.
# Path separators and control characters remain rejected to prevent traversal.
_SAFE_FILE_NAME = re.compile(r"[^\x00-\x1f\x7f/\\]{1,255}")
_MAX_LIBRARY_CONTENT_LENGTH = 8_000_000
_LIBRARY_UPLOAD_CHUNK_SIZE = 2 * 1024 * 1024
# Never return multi-megabyte text blobs to the interactive Library pane.  The
# original file remains privately downloadable from object storage; this limit
# only bounds browser-facing preview/edit data.
_MAX_LIBRARY_INLINE_PREVIEW_CHARS = 512 * 1024
_MAX_LIBRARY_EXPORT_FILES = 100
_MAX_LIBRARY_EXPORT_BYTES = 250 * 1024 * 1024
_MAX_EDITABLE_OFFICE_CHARS = 8_000_000
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
    "text/x-markdown",
    "text/tab-separated-values",
    "text/xml",
    "application/javascript",
    "application/json",
    "application/sql",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/x-ipynb+json",
    "application/x-sh",
    "application/typescript",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/msword",
    "application/vnd.ms-word",
    "application/vnd.ms-powerpoint",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.presentation",
    "application/rtf",
    "text/rtf",
    "application/pdf",
    "application/zip",
    "application/gzip",
    "application/x-gzip",
    "application/x-tar",
    "application/x-7z-compressed",
    "application/x-rar-compressed",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.oasis.opendocument.spreadsheet",
    "image/svg+xml",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/tiff",
    "image/bmp",
    "image/avif",
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-m4v",
    "video/x-msvideo",
    "video/x-matroska",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "audio/x-wav",
    "audio/flac",
    "audio/x-m4a",
    "application/octet-stream",
}
_EXTRACTABLE_LIBRARY_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.presentation",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/msword",
    "application/vnd.ms-word",
    "text/csv",
    "text/tab-separated-values",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/json",
    "application/x-ipynb+json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/rtf",
    "text/rtf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/webp",
    "image/bmp",
    "image/gif",
}


def _content_type_for_name(name: str) -> str:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {
        "md": "text/markdown",
        "mdx": "text/markdown",
        "json": "application/json",
        "csv": "text/csv",
        "tsv": "text/tab-separated-values",
        "yaml": "application/yaml",
        "yml": "application/yaml",
        "toml": "text/plain",
        "ini": "text/plain",
        "cfg": "text/plain",
        "log": "text/plain",
        "xml": "application/xml",
        "html": "text/html",
        "htm": "text/html",
        "xhtml": "text/html",
        "css": "text/css",
        "sql": "text/sql",
        "py": "text/x-python",
        "ipynb": "application/x-ipynb+json",
        "js": "text/javascript",
        "ts": "text/javascript",
        "tsx": "text/javascript",
        "jsx": "text/javascript",
        "mjs": "text/javascript",
        "cjs": "text/javascript",
        "sh": "application/x-sh",
        "bash": "application/x-sh",
        "java": "text/x-java",
        "go": "text/plain",
        "rs": "text/plain",
        "c": "text/plain",
        "h": "text/plain",
        "cpp": "text/plain",
        "cc": "text/plain",
        "cxx": "text/plain",
        "diff": "text/x-diff",
        "patch": "text/x-diff",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt": "application/vnd.ms-powerpoint",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "odt": "application/vnd.oasis.opendocument.text",
        "odp": "application/vnd.oasis.opendocument.presentation",
        "rtf": "application/rtf",
        "zip": "application/zip",
        "tar": "application/x-tar",
        "gz": "application/gzip",
        "tgz": "application/gzip",
        "7z": "application/x-7z-compressed",
        "rar": "application/x-rar-compressed",
        "svg": "image/svg+xml",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
        "bmp": "image/bmp",
        "avif": "image/avif",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
        "m4v": "video/x-m4v",
        "avi": "video/x-msvideo",
        "mkv": "video/x-matroska",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "ogg": "audio/ogg",
        "m4a": "audio/x-m4a",
        "flac": "audio/flac",
    }.get(extension, "text/plain")


def _content_disposition(*, disposition: str, filename: str) -> str:
    """Build a Latin-1-safe Content-Disposition for arbitrary Unicode names."""

    clean_name = "".join(char for char in filename if char.isprintable()).strip() or "file"
    ascii_name = "".join(
        char if ord(char) < 128 and char not in {"\\", '"'} and not char.isspace() else "_"
        for char in clean_name
    )
    ascii_name = re.sub(r"_+", "_", ascii_name).strip(" ._") or "file"
    return (
        f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(clean_name, safe='')}"
    )


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
    content_truncated: bool = False
    download_url: str | None = None
    archive_entries: list[dict[str, object]] | None = None
    dataset_profile: dict[str, object] | None = None

    model_config = ConfigDict(extra="forbid")


class WorkspaceCsvPageSchema(BaseModel):
    """A bounded, authorized page of a CSV stored in the Library."""

    columns: list[str]
    rows: list[list[str]]
    offset: int
    limit: int
    has_more: bool

    model_config = ConfigDict(extra="forbid")


class DatasetQuerySchema(BaseModel):
    columns: list[str] | None = Field(default=None, max_length=50)
    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=10_000_000)
    order_by: str | None = Field(default=None, max_length=255)
    descending: bool = False
    filters: list[DatasetFilterSchema] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(extra="forbid")


class DatasetQueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]
    offset: int
    has_more: bool

    model_config = ConfigDict(extra="forbid")


class DatasetFilterSchema(BaseModel):
    """A parameterized filter; arbitrary SQL is deliberately not accepted."""

    column: str = Field(min_length=1, max_length=255)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains"]
    value: str | int | float | bool

    model_config = ConfigDict(extra="forbid")


class DatasetAggregateSchema(BaseModel):
    metric: Literal["count", "sum", "avg", "min", "max"]
    column: str = Field(min_length=1, max_length=255)
    group_by: str | None = Field(default=None, max_length=255)
    filters: list[DatasetFilterSchema] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=100, ge=1, le=500)

    model_config = ConfigDict(extra="forbid")


class DatasetAggregateResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]

    model_config = ConfigDict(extra="forbid")


def _text_as_export_html(text: str, title: str) -> str:
    """Convert bounded user text to escaped HTML for the shared exporters."""
    blocks: list[str] = [f"<h1>{html.escape(title)}</h1>"]
    for line in text.splitlines():
        if line.startswith("### "):
            blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            blocks.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.strip():
            blocks.append(f"<p>{html.escape(line)}</p>")
        else:
            blocks.append("<p></p>")
    return "".join(blocks)


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
            code="CONVERSATION_NOT_FOUND",
            message="DeepSpace workspace not found",
            status_code=404,
        )
    return conversation


def _serialize_file(
    file: DeepSpaceWorkspaceFile, *, include_content: bool = False
) -> WorkspaceFileSchema:
    metadata = getattr(file, "metadata_json", None)
    raw_content = file.content if include_content and not file.is_binary else None
    raw_extracted_text = file.extracted_text if include_content else None
    content_truncated = bool(
        (raw_content and len(raw_content) > _MAX_LIBRARY_INLINE_PREVIEW_CHARS)
        or (raw_extracted_text and len(raw_extracted_text) > _MAX_LIBRARY_INLINE_PREVIEW_CHARS)
    )
    content = raw_content[:_MAX_LIBRARY_INLINE_PREVIEW_CHARS] if raw_content is not None else None
    extracted_text = (
        raw_extracted_text[:_MAX_LIBRARY_INLINE_PREVIEW_CHARS]
        if raw_extracted_text is not None
        else None
    )
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
        extracted_text=extracted_text,
        content_truncated=content_truncated,
        download_url=(
            f"/api/v1/deepspace/library/{file.conversation_id}/files/{file.id}/content"
            if file.is_binary
            else None
        ),
        dataset_profile=(
            cast(dict[str, object], metadata.get("dataset_profile"))
            if isinstance(metadata, dict) and isinstance(metadata.get("dataset_profile"), dict)
            else None
        ),
    )


def _folder_schema(folder: DeepSpaceWorkspaceFolder) -> WorkspaceFolderSchema:
    return WorkspaceFolderSchema(
        id=str(folder.id),
        name=folder.name,
        parent_folder_id=(str(folder.parent_folder_id) if folder.parent_folder_id else None),
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
    # Browsers commonly report unknown/legacy files as octet-stream. Prefer a
    # deterministic extension mapping so valid Office, data, and media files
    # retain their real type and can be extracted/previewed correctly.
    inferred_content_type = _content_type_for_name(payload.name)
    if content_type == "application/octet-stream" or content_type not in _LIBRARY_CONTENT_TYPES:
        if inferred_content_type != "text/plain" or content_type not in _LIBRARY_CONTENT_TYPES:
            content_type = inferred_content_type
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
            code="INVALID_CHUNK",
            message="The upload chunk number is invalid.",
            status_code=422,
        )
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > upload.chunk_size:
                raise ApiError(
                    code="INVALID_CHUNK",
                    message="The upload chunk is too large.",
                    status_code=413,
                )
        except ValueError:
            raise ApiError(
                code="INVALID_CHUNK",
                message="The upload chunk length is invalid.",
                status_code=422,
            ) from None
    body_parts: list[bytes] = []
    body_size = 0
    async for part in request.stream():
        body_size += len(part)
        if body_size > upload.chunk_size:
            raise ApiError(
                code="INVALID_CHUNK",
                message="The upload chunk is too large.",
                status_code=413,
            )
        body_parts.append(part)
    body = b"".join(body_parts)
    expected_length = min(upload.chunk_size, upload.expected_size - chunk_index * upload.chunk_size)
    if len(body) != expected_length or len(body) > upload.chunk_size:
        raise ApiError(
            code="INVALID_CHUNK",
            message="The upload chunk size is invalid.",
            status_code=422,
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
            code="UPLOAD_CANCELLED",
            message="This upload was cancelled.",
            status_code=409,
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
            code="UPLOAD_QUEUE_UNAVAILABLE",
            message=upload.error_message,
            status_code=503,
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
            tenant_id=auth.tenant_id,
            upload_id=upload.id,
            total_chunks=upload.total_chunks,
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
                DeepSpaceWorkspaceFile.updated_at.desc(),
                DeepSpaceWorkspaceFile.created_at.desc(),
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
                code="INVALID_REQUEST",
                message="A folder cannot contain itself.",
                status_code=422,
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
                db=db,
                auth=auth,
                conversation_id=conversation_id,
                folder_id=cursor.parent_folder_id,
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
            code="INVALID_REQUEST",
            message="A file may only be selected once.",
            status_code=422,
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
    archive_entries: list[dict[str, Any]] | None = None
    if file.is_binary and file.storage_bucket and file.storage_key:
        try:
            storage = StorageService(settings)
            payload: bytes | None = None
            if file.extracted_text is None and file.content_type in _EXTRACTABLE_LIBRARY_TYPES:
                # Older uploads could be stored successfully when optional
                # extraction failed. Reprocess once on first open so the
                # preview and document tools recover without requiring a
                # re-upload.
                payload = storage.get_bytes(bucket=file.storage_bucket, object_key=file.storage_key)
                extraction = LibraryStorageService(settings).extract(
                    filename=file.name,
                    content_type=file.content_type,
                    payload=payload,
                    tenant_id=auth.tenant_id,
                )
                if extraction.get("text"):
                    file.extracted_text = str(extraction["text"])
                    db.commit()
            if file.content_type == "application/zip":
                if payload is None:
                    payload = storage.get_bytes(
                        bucket=file.storage_bucket, object_key=file.storage_key
                    )
                archive_entries = safe_archive_entries(payload)
        except StorageServiceError as exc:
            raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc
    result = _serialize_file(file, include_content=True)
    if archive_entries is not None:
        result.archive_entries = archive_entries
    return result


@router.get(
    "/{conversation_id}/files/{file_id}/export",
    response_model=None,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def export_workspace_file(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    format: Literal["original", "txt", "md", "pdf", "docx", "pptx", "xlsx"] = Query("original"),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Export one authorized Library file to a compatible user-selected format."""
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    source = file.content if not file.is_binary else file.extracted_text
    original_payload: bytes | None = None
    if file.is_binary and file.storage_bucket and file.storage_key:
        original_payload = _library_file_payload(file=file, settings=settings)
    if format == "original":
        if original_payload is None:
            original_payload = (source or "").encode("utf-8")
        payload = original_payload
        media_type = file.content_type
        extension = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else "txt"
    else:
        text = source or ""
        if len(text) > _MAX_EDITABLE_OFFICE_CHARS:
            raise ApiError(
                code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                message="The file is too large to convert safely.",
                status_code=413,
            )
        if format in {"txt", "md"}:
            payload = text.encode("utf-8")
            media_type = "text/plain" if format == "txt" else "text/markdown"
            extension = format
        else:
            service = DeepSpaceExportService()
            title = file.name.rsplit(".", 1)[0]
            html_content = _text_as_export_html(text, title)
            if format == "pdf":
                payload = service.generate_pdf(html_content, title).getvalue()
                media_type, extension = "application/pdf", "pdf"
            elif format == "docx":
                payload = text_to_docx(text)
                media_type, extension = (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "docx",
                )
            elif format == "xlsx":
                payload = text_to_xlsx(text)
                media_type, extension = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "xlsx",
                )
            else:
                payload = text_to_pptx(text)
                media_type, extension = (
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "pptx",
                )
    stem = file.name.rsplit(".", 1)[0] if "." in file.name else file.name
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": _content_disposition(
                disposition="attachment", filename=f"{stem}.{extension}"
            ),
        },
    )


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
        metadata_json=(
            {"dataset_profile": {"status": "queued"}}
            if DatasetDerivativeService.supports(decoded.content_type)
            else {}
        ),
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
    if DatasetDerivativeService.supports(file.content_type):
        profile_library_dataset.delay(file_id=str(file.id), tenant_id=str(auth.tenant_id))
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
    old_binary_payload: bytes | None = None
    generated_binary: bytes | None = None
    if payload.content is not None:
        if file.is_binary:
            if file.content_type not in {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }:
                raise ApiError(
                    code="VALIDATION_ERROR",
                    message="This binary format cannot be edited in the browser.",
                    status_code=422,
                )
            if len(payload.content) > _MAX_EDITABLE_OFFICE_CHARS:
                raise ApiError(
                    code="DOCUMENT_TEXT_LIMIT_EXCEEDED",
                    message="The edited document is too large.",
                    status_code=413,
                )
            old_binary_payload = _library_file_payload(file=file, settings=settings)
            if file.content_type.endswith("wordprocessingml.document"):
                generated_binary = text_to_docx(payload.content)
            elif file.content_type.endswith("presentationml.presentation"):
                generated_binary = text_to_pptx(payload.content)
            else:
                generated_binary = text_to_xlsx(payload.content)
            if len(generated_binary) > settings.upload_max_bytes:
                raise ApiError(
                    code="DOC_TOO_LARGE", message="The edited file is too large.", status_code=413
                )
            try:
                stored = StorageService(settings).put_bytes(
                    tenant_id=auth.tenant_id,
                    document_id=file.id,
                    filename=file.name,
                    content_type=file.content_type,
                    payload=generated_binary,
                )
                file.storage_bucket = stored.bucket
                file.storage_key = stored.object_key
            except StorageServiceError as exc:
                raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc
            file.extracted_text = payload.content
            file.size_bytes = len(generated_binary)
            file.checksum_sha256 = hashlib.sha256(generated_binary).hexdigest()
        else:
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
        if old_binary_payload is not None:
            try:
                StorageService(settings).put_bytes(
                    tenant_id=auth.tenant_id,
                    document_id=file.id,
                    filename=file.name,
                    content_type=file.content_type,
                    payload=old_binary_payload,
                )
            except StorageServiceError:
                pass
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
            filename=name,
            content_type=content_type,
            payload=payload,
            tenant_id=auth.tenant_id,
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
        clone.metadata_json = {
            **(source.metadata_json or {}),
            "copied_from": str(source.id),
        }
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
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Disposition": _content_disposition(disposition=disposition, filename=file.name),
    }
    payload = _library_file_payload(file=file, settings=settings)
    if not file.is_binary:
        return PlainTextResponse(
            payload.decode("utf-8", errors="replace"),
            media_type=file.content_type,
            headers=headers,
        )
    headers["Content-Length"] = str(len(payload))
    return StreamingResponse(iter([payload]), media_type=file.content_type, headers=headers)


@router.get(
    "/{conversation_id}/files/{file_id}/csv-page",
    response_model=WorkspaceCsvPageSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def read_workspace_csv_page(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    offset: int = Query(default=0, ge=0, le=10_000_000),
    limit: int = Query(default=200, ge=1, le=500),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WorkspaceCsvPageSchema:
    """Return one bounded CSV page without returning the full data set to the browser."""
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    if file.content_type not in {"text/csv", "text/x-csv", "text/tab-separated-values"}:
        raise ApiError(
            code="INVALID_REQUEST", message="The selected file is not a CSV table.", status_code=422
        )
    profile = (
        file.metadata_json.get("dataset_profile") if isinstance(file.metadata_json, dict) else None
    )
    if isinstance(profile, dict) and profile.get("status") == "ready":
        result = DatasetDerivativeService(settings).query(
            profile=profile,
            columns=None,
            limit=limit,
            offset=offset,
            order_by=None,
            descending=False,
        )
        columns = [str(column) for column in result["columns"]]
        parquet_rows = [
            ["" if value is None else str(value) for value in row.values()]
            for row in result["rows"]
        ]
        return WorkspaceCsvPageSchema(
            columns=columns,
            rows=parquet_rows,
            offset=offset,
            limit=limit,
            has_more=bool(result["has_more"]),
        )
    delimiter = "\t" if file.content_type == "text/tab-separated-values" else ","
    payload = _library_file_payload(file=file, settings=settings)
    # csv.reader handles quoted newlines and escaped delimiters correctly. Only
    # the requested page plus one sentinel row is retained in the response.
    reader = csv.reader(
        io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8-sig", errors="replace", newline=""),
        delimiter=delimiter,
    )
    columns = next(reader, [])
    for _ in range(offset):
        if next(reader, None) is None:
            return WorkspaceCsvPageSchema(
                columns=columns, rows=[], offset=offset, limit=limit, has_more=False
            )
    rows: list[list[str]] = []
    for _ in range(limit):
        row = next(reader, None)
        if row is None:
            return WorkspaceCsvPageSchema(
                columns=columns, rows=rows, offset=offset, limit=limit, has_more=False
            )
        rows.append(row[:50])
    return WorkspaceCsvPageSchema(
        columns=columns[:50],
        rows=rows,
        offset=offset,
        limit=limit,
        has_more=next(reader, None) is not None,
    )


@router.post(
    "/{conversation_id}/files/{file_id}/dataset-query",
    response_model=DatasetQueryResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def query_workspace_dataset(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: DatasetQuerySchema,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DatasetQueryResponse:
    """Serve bounded read-only dataset pages from a private Parquet derivative."""
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    profile = (
        file.metadata_json.get("dataset_profile") if isinstance(file.metadata_json, dict) else None
    )
    if not isinstance(profile, dict) or profile.get("status") != "ready":
        raise ApiError(
            code="DATASET_NOT_READY", message="Dataset is still processing.", status_code=409
        )
    result = DatasetDerivativeService(settings).query(
        profile=profile,
        columns=payload.columns,
        limit=payload.limit,
        offset=payload.offset,
        order_by=payload.order_by,
        descending=payload.descending,
        filters=[item.model_dump() for item in payload.filters],
    )
    return DatasetQueryResponse(**result)


@router.post(
    "/{conversation_id}/files/{file_id}/dataset-aggregate",
    response_model=DatasetAggregateResponse,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def aggregate_workspace_dataset(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: DatasetAggregateSchema,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DatasetAggregateResponse:
    """Return a bounded server-side aggregate suitable for a table or chart."""
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    profile = (
        file.metadata_json.get("dataset_profile") if isinstance(file.metadata_json, dict) else None
    )
    if not isinstance(profile, dict) or profile.get("status") != "ready":
        raise ApiError(
            code="DATASET_NOT_READY", message="Dataset is still processing.", status_code=409
        )
    return DatasetAggregateResponse(
        **DatasetDerivativeService(settings).aggregate(
            profile=profile,
            metric=payload.metric,
            column=payload.column,
            group_by=payload.group_by,
            filters=[item.model_dump() for item in payload.filters],
            limit=payload.limit,
        )
    )


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
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    if content_type.startswith(
        ("text/", "application/json", "application/xml", "application/yaml")
    ):
        return PlainTextResponse(
            payload.decode("utf-8", errors="replace"),
            media_type=content_type,
            headers=headers,
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
