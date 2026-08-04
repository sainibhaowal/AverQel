"""Tenant-scoped files visible in the DeepSpace Library drawer."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.errors import ApiError
from app.deepspace.models.conversation import Conversation
from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.platform.database.session import get_db

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


class WorkspaceFileSchema(BaseModel):
    id: str
    name: str
    content_type: str
    source: str
    size_bytes: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    content: str | None = None

    model_config = ConfigDict(extra="forbid")


class WorkspaceFileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(default="", max_length=_MAX_LIBRARY_CONTENT_LENGTH)
    content_type: str = Field(default="text/markdown", max_length=127)

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

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def safe_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return WorkspaceFileCreate.safe_name(value)


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
    return WorkspaceFileSchema(
        id=str(file.id),
        name=file.name,
        content_type=file.content_type,
        source=file.source,
        size_bytes=file.size_bytes,
        created_at=file.created_at,
        updated_at=file.updated_at,
        content=file.content if include_content else None,
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
    "/{conversation_id}/files/{file_id}",
    response_model=WorkspaceFileSchema,
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def get_workspace_file(
    conversation_id: uuid.UUID,
    file_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
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
    return _serialize_file(file, include_content=True)


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
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
    file = DeepSpaceWorkspaceFile(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=conversation_id,
        name=payload.name,
        content_type=payload.content_type,
        content=payload.content,
        size_bytes=len(payload.content.encode("utf-8")),
        source="user",
    )
    db.add(file)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            code="CONFLICT",
            message="A file with that name already exists in this workspace",
            status_code=409,
        ) from exc
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
) -> WorkspaceFileSchema:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
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
    if payload.name is not None:
        file.name = payload.name
    if payload.content is not None:
        file.content = payload.content
        file.size_bytes = len(payload.content.encode("utf-8"))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(
            code="CONFLICT",
            message="A file with that name already exists in this workspace",
            status_code=409,
        ) from exc
    db.refresh(file)
    return _serialize_file(file, include_content=True)


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
) -> None:
    _conversation(db=db, auth=auth, conversation_id=conversation_id)
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
    db.delete(file)
    db.commit()
