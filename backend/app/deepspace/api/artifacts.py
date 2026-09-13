"""Authenticated delivery for provider-generated DeepSpace media."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.deepspace.models.artifact_job import DeepSpaceArtifactJob
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.deepspace.workers.tasks import create_artifact_task
from app.platform.database.session import get_db
from app.system.services.storage_service import StorageService, StorageServiceError

router = APIRouter(prefix="/deepspace/artifacts", tags=["deepspace-artifacts"])
_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
_ARTIFACT_CONTENT_TYPES = {
    "text/markdown",
    "text/plain",
    "text/html",
    "text/csv",
    "application/json",
    "image/svg+xml",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class ArtifactJobCreate(BaseModel):
    conversation_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    format: str = Field(pattern="^(markdown|csv|json|html|text)$")
    content: str = Field(min_length=1, max_length=100_000)


def _job_payload(job: DeepSpaceArtifactJob) -> dict[str, object]:
    return {
        "id": str(job.id),
        "conversation_id": str(job.conversation_id),
        "filename": job.filename,
        "format": job.format,
        "status": job.status,
        "file_id": str(job.file_id) if job.file_id else None,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/jobs", dependencies=[Depends(require_permissions("queries:run"))])
def create_artifact_job(
    payload: ArtifactJobCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    from app.deepspace.models.conversation import Conversation

    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == auth.tenant_id,
            Conversation.user_id == auth.user_id,
            Conversation.kind == "deepspace",
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ApiError(
            code="CONVERSATION_NOT_FOUND",
            message="DeepSpace conversation not found",
            status_code=404,
        )
    job = DeepSpaceArtifactJob(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        conversation_id=payload.conversation_id,
        filename=payload.filename.strip(),
        format=payload.format,
        content=payload.content,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    create_artifact_task.delay(
        job_id=str(job.id), tenant_id=str(auth.tenant_id), user_id=str(auth.user_id)
    )
    return _job_payload(job)


@router.get("/jobs", dependencies=[Depends(require_permissions("queries:run"))])
def list_artifact_jobs(
    auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    jobs = (
        db.execute(
            select(DeepSpaceArtifactJob)
            .where(
                DeepSpaceArtifactJob.tenant_id == auth.tenant_id,
                DeepSpaceArtifactJob.user_id == auth.user_id,
            )
            .order_by(DeepSpaceArtifactJob.created_at.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    return [_job_payload(job) for job in jobs]


def _artifact(*, db: Session, auth: AuthContext, artifact_id: uuid.UUID) -> DeepSpaceMediaArtifact:
    artifact = db.execute(
        select(DeepSpaceMediaArtifact).where(
            DeepSpaceMediaArtifact.id == artifact_id,
            DeepSpaceMediaArtifact.tenant_id == auth.tenant_id,
            DeepSpaceMediaArtifact.user_id == auth.user_id,
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise ApiError(code="NOT_FOUND", message="DeepSpace artifact not found", status_code=404)
    return artifact


def _parse_range(range_header: str | None, *, total: int) -> tuple[int, int] | None:
    if not range_header:
        return None
    match = _RANGE_PATTERN.fullmatch(range_header.strip())
    if match is None:
        raise ApiError(code="INVALID_REQUEST", message="Invalid media byte range", status_code=416)
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise ApiError(code="INVALID_REQUEST", message="Invalid media byte range", status_code=416)
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else total - 1
    else:
        requested_size = int(end_text)
        if requested_size <= 0:
            raise ApiError(
                code="INVALID_REQUEST",
                message="Invalid media byte range",
                status_code=416,
            )
        start = max(0, total - requested_size)
        end = total - 1
    if start < 0 or end < start or start >= total:
        raise ApiError(
            code="INVALID_REQUEST",
            message="Requested media range is unavailable",
            status_code=416,
        )
    return start, min(end, total - 1)


def _chunk_bytes(payload: bytes, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    for offset in range(0, len(payload), chunk_size):
        yield payload[offset : offset + chunk_size]


@router.get(
    "/{artifact_id}/content",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def stream_artifact(
    artifact_id: uuid.UUID,
    range_header: str | None = Header(default=None, alias="Range"),
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Deliver a media artifact only after tenant and user ownership checks.

    Browser media controls use HTTP ranges for seeking.  Range processing is
    intentionally performed after authorization and against the immutable size
    stored when the provider output was persisted.
    """

    artifact = _artifact(db=db, auth=auth, artifact_id=artifact_id)
    if (
        not artifact.content_type.startswith(("image/", "video/", "audio/", "text/"))
        and artifact.content_type not in _ARTIFACT_CONTENT_TYPES
    ):
        raise ApiError(
            code="NOT_FOUND",
            message="DeepSpace artifact has an unsupported media type",
            status_code=404,
        )
    try:
        payload = StorageService(settings).get_bytes(
            bucket=artifact.storage_bucket,
            object_key=artifact.storage_key,
        )
    except StorageServiceError as exc:
        raise ApiError(code=exc.code, message=exc.message, status_code=503) from exc

    # Object storage is authoritative; avoid sending stale or malformed bytes.
    total = len(payload)
    if total == 0:
        raise ApiError(
            code="STORAGE_OBJECT_NOT_FOUND",
            message="Generated media is empty",
            status_code=404,
        )
    byte_range = _parse_range(range_header, total=total)
    safe_filename = re.sub(r'[\r\n"]+', "", artifact.title).strip() or "generated-media"
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="{safe_filename}"',
    }
    if artifact.content_type in {"text/html", "image/svg+xml"}:
        headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
        )
    if byte_range is None:
        headers["Content-Length"] = str(total)
        return StreamingResponse(
            _chunk_bytes(payload), media_type=artifact.content_type, headers=headers
        )

    start, end = byte_range
    body = payload[start : end + 1]
    headers["Content-Length"] = str(len(body))
    headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return StreamingResponse(
        _chunk_bytes(body),
        status_code=206,
        media_type=artifact.content_type,
        headers=headers,
    )
