"""Tenant-scoped files visible in the DeepSpace Library drawer."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
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
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.deepspace.models.workspace_folder import DeepSpaceWorkspaceFolder
from app.deepspace.services.library_storage import (
    LibraryStorageService,
    decode_library_payload,
    read_archive_entry,
    safe_archive_entries,
)
from app.platform.database.session import get_db
from app.system.services.storage_service import StorageService, StorageServiceError

router = APIRouter(prefix="/deepspace/library", tags=["deepspace-library"])
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")
_MAX_LIBRARY_CONTENT_LENGTH = 8_000_000
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
    file.name = snapshot.name
    file.content_type = snapshot.content_type
    file.content = snapshot.content
    file.storage_bucket = snapshot.storage_bucket
    file.storage_key = snapshot.storage_key
    file.checksum_sha256 = snapshot.checksum_sha256
    file.size_bytes = snapshot.size_bytes
    file.is_binary = snapshot.content is None
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
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse | PlainTextResponse:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = _owned_file(db=db, auth=auth, conversation_id=conversation_id, file_id=file_id)
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Disposition": f'inline; filename="{file.name.replace(chr(34), "")}"',
    }
    if not file.is_binary:
        return PlainTextResponse(file.content or "", media_type=file.content_type, headers=headers)
    if not file.storage_bucket or not file.storage_key:
        raise ApiError(
            code="STORAGE_OBJECT_NOT_FOUND",
            message="Library file payload is missing.",
            status_code=404,
        )
    try:
        payload = StorageService(settings).get_bytes(
            bucket=file.storage_bucket, object_key=file.storage_key
        )
    except StorageServiceError as exc:
        raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc
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
