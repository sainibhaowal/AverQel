"""Authenticated delivery for provider-generated DeepSpace media."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.platform.database.session import get_db
from app.system.services.storage_service import StorageService, StorageServiceError

router = APIRouter(prefix="/deepspace/artifacts", tags=["deepspace-artifacts"])
_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


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
                code="INVALID_REQUEST", message="Invalid media byte range", status_code=416
            )
        start = max(0, total - requested_size)
        end = total - 1
    if start < 0 or end < start or start >= total:
        raise ApiError(
            code="INVALID_REQUEST", message="Requested media range is unavailable", status_code=416
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
    if not artifact.content_type.startswith(("image/", "video/", "audio/")):
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
            code="STORAGE_OBJECT_NOT_FOUND", message="Generated media is empty", status_code=404
        )
    byte_range = _parse_range(range_header, total=total)
    safe_filename = re.sub(r'[\r\n"]+', "", artifact.title).strip() or "generated-media"
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'inline; filename="{safe_filename}"',
    }
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
        _chunk_bytes(body), status_code=206, media_type=artifact.content_type, headers=headers
    )
