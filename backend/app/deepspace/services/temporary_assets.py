"""Lifecycle helpers for short-lived, conversation-owned image imports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deepspace.models.workspace_file import DeepSpaceWorkspaceFile
from app.deepspace.models.workspace_file_version import DeepSpaceWorkspaceFileVersion
from app.system.models.storage_cleanup import StorageCleanupJob

TEMPORARY_ASSET_TTL = timedelta(days=30)


def temporary_asset_expiration(*, now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + TEMPORARY_ASSET_TTL


def temporary_asset_is_expired(
    metadata: dict[str, Any] | None, *, now: datetime | None = None
) -> bool:
    """Return true only for a parseable, elapsed expiry timestamp."""
    expires_at = metadata.get("expires_at") if isinstance(metadata, dict) else None
    if not isinstance(expires_at, str):
        return False
    try:
        expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    return expiration <= (now or datetime.now(UTC))


def cleanup_expired_temporary_assets(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    """Delete expired temporary asset records and enqueue their object blobs.

    Object deletion is deferred to ``maintenance.storage_cleanup`` so a
    transient object-store error cannot leave a live database row pointing at
    missing content. The caller owns the transaction and tenant RLS context.
    """
    current_time = now or datetime.now(UTC)
    candidates = list(
        db.execute(
            select(DeepSpaceWorkspaceFile)
            .where(
                DeepSpaceWorkspaceFile.tenant_id == tenant_id,
                DeepSpaceWorkspaceFile.source == "temporary_asset",
            )
            .order_by(DeepSpaceWorkspaceFile.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    expired = [
        file
        for file in candidates
        if temporary_asset_is_expired(file.metadata_json, now=current_time)
        or _fallback_asset_expired(file, current_time)
    ]
    if not expired:
        return 0

    file_ids = [file.id for file in expired]
    versions = list(
        db.execute(
            select(DeepSpaceWorkspaceFileVersion).where(
                DeepSpaceWorkspaceFileVersion.tenant_id == tenant_id,
                DeepSpaceWorkspaceFileVersion.file_id.in_(file_ids),
            )
        )
        .scalars()
        .all()
    )
    blobs = {
        (file.storage_bucket, file.storage_key, file.user_id)
        for file in expired
        if file.storage_bucket and file.storage_key
    }
    blobs.update(
        (version.storage_bucket, version.storage_key, version.user_id)
        for version in versions
        if version.storage_bucket and version.storage_key
    )
    for bucket, key, owner_user_id in blobs:
        db.add(
            StorageCleanupJob(
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                bucket=str(bucket),
                object_key=str(key),
                status="pending",
            )
        )
    for file in expired:
        db.delete(file)
    db.flush()
    return len(expired)


def _fallback_asset_expired(file: DeepSpaceWorkspaceFile, now: datetime) -> bool:
    """Bound retention even if legacy or damaged metadata has no expiry."""
    created_at = file.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at + TEMPORARY_ASSET_TTL <= now
