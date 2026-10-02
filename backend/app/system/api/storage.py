from __future__ import annotations

import uuid
from datetime import UTC, datetime

import redis
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.roles import is_admin_role
from app.core.config import get_settings
from app.core.errors import ApiError
from app.platform.database.session import get_db
from app.realtime.event_bus import publish_event_sync
from app.system.schemas.plans import (
    CurrentPlanSchema,
    StorageArchiveSchema,
    StorageDetailsSchema,
    StorageMetricSchema,
    StorageReconciliationSchema,
    StorageRetentionPolicySchema,
    StorageRetentionPreviewSchema,
    StorageRetentionUpdateSchema,
    StorageUsageSchema,
)
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_lifecycle_adapters import StorageLifecycleAdapterService
from app.system.services.storage_quota import StorageQuotaService, resolve_storage_plan

router = APIRouter(prefix="/storage", tags=["storage"])


def _publish_storage_event(auth: AuthContext, event_type: str, data: dict[str, object]) -> None:
    """Notify live clients after a committed lifecycle mutation.

    The REST response remains authoritative and this best-effort notification
    must never turn a successful storage mutation into a failed request.
    """
    client = redis.from_url(get_settings().redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    try:
        publish_event_sync(
            client,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            event_type=event_type,
            resource="storage",
            data=data,
        )
    except Exception:
        return
    finally:
        client.close()


def _retention_policy_response(service: StorageLifecycleService, tenant_id):
    policy = service.policy(tenant_id=tenant_id)
    return StorageRetentionPolicySchema(
        mode=policy.mode,
        days=policy.days,
        policy_version=policy.version,
        automatic_purge_enabled=False,
    )


@router.get("/retention", response_model=StorageRetentionPolicySchema)
def get_storage_retention_policy(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageRetentionPolicySchema:
    return _retention_policy_response(StorageLifecycleService(db), auth.tenant_id)


@router.put("/retention", response_model=StorageRetentionPolicySchema)
def update_storage_retention_policy(
    payload: StorageRetentionUpdateSchema,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageRetentionPolicySchema:
    # The endpoint accepts only the four user-facing values. Purge is never
    # enabled by this setting, and all changes stay tenant-scoped.
    try:
        policy = StorageLifecycleService(db).set_policy(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            mode=payload.mode,
        )
    except ValueError as exc:
        raise ApiError(code="INVALID_REQUEST", message=str(exc), status_code=422) from exc
    _publish_storage_event(auth, "storage.retention.updated", {"mode": policy.mode})
    return StorageRetentionPolicySchema(
        mode=policy.mode,
        days=policy.days,
        policy_version=policy.version,
        automatic_purge_enabled=False,
    )


@router.get("/retention/preview", response_model=StorageRetentionPreviewSchema)
def preview_storage_retention(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageRetentionPreviewSchema:
    service = StorageLifecycleService(db)
    preview = service.preview(tenant_id=auth.tenant_id)
    policy = service.policy(tenant_id=auth.tenant_id)
    return StorageRetentionPreviewSchema(
        policy=StorageRetentionPolicySchema(
            mode=policy.mode,
            days=policy.days,
            policy_version=policy.version,
            automatic_purge_enabled=False,
        ),
        run_id=str(preview.run_id) if preview.run_id else None,
        cutoff=preview.cutoff.isoformat() if preview.cutoff else None,
        candidate_count=preview.candidate_count,
        candidate_bytes=preview.candidate_bytes,
        protected_count=preview.protected_count,
        legacy_data_preserved=preview.legacy_data_preserved,
    )


def _archive_response(manifest) -> StorageArchiveSchema:
    return StorageArchiveSchema(
        item_id=str(manifest.lifecycle_item_id),
        category=manifest.category,
        source_type=manifest.source_type,
        state=manifest.state,
        archived_at=manifest.archived_at.isoformat(),
        restored_at=manifest.restored_at.isoformat() if manifest.restored_at else None,
    )


@router.post("/reconcile", response_model=StorageReconciliationSchema)
def reconcile_storage(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageReconciliationSchema:
    """Refresh lifecycle identities and report drift without deleting data."""
    run = StorageLifecycleAdapterService(db).reconcile_tenant(tenant_id=auth.tenant_id)
    totals = run.category_totals_json if isinstance(run.category_totals_json, dict) else {}
    return StorageReconciliationSchema(
        run_id=str(run.id),
        status=run.status,
        mismatch_count=run.mismatch_count,
        category_totals=totals,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )


@router.post("/archives/{item_id}", response_model=StorageArchiveSchema)
def archive_storage_item(
    item_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageArchiveSchema:
    try:
        manifest = StorageLifecycleService(db).archive_item(
            tenant_id=auth.tenant_id,
            item_id=item_id,
            user_id=auth.user_id,
            is_admin=is_admin_role(auth.roles),
        )
        db.commit()
        _publish_storage_event(
            auth, "storage.archive.updated", {"item_id": str(item_id), "state": "archived"}
        )
        return _archive_response(manifest)
    except ValueError as exc:
        db.rollback()
        raise ApiError(code="INVALID_REQUEST", message=str(exc), status_code=422) from exc


@router.post("/archives/{item_id}/restore", response_model=StorageArchiveSchema)
def restore_storage_item(
    item_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageArchiveSchema:
    try:
        manifest = StorageLifecycleService(db).restore_item(
            tenant_id=auth.tenant_id,
            item_id=item_id,
            user_id=auth.user_id,
            is_admin=is_admin_role(auth.roles),
        )
        db.commit()
        _publish_storage_event(
            auth, "storage.archive.updated", {"item_id": str(item_id), "state": "restored"}
        )
        return _archive_response(manifest)
    except ValueError as exc:
        db.rollback()
        raise ApiError(code="INVALID_REQUEST", message=str(exc), status_code=422) from exc


@router.get("/current", response_model=StorageDetailsSchema)
def get_storage_details(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StorageDetailsSchema:
    quota = StorageQuotaService(db)
    current = resolve_storage_plan(auth.roles)
    usage = quota.usage(tenant_id=auth.tenant_id)
    metrics = quota.metrics(tenant_id=auth.tenant_id)
    return StorageDetailsSchema(
        current_plan=CurrentPlanSchema(
            id=current.id,
            name=current.name,
            storage_limit_bytes=current.storage_limit_bytes,
            description=current.description,
            admin_account=is_admin_role(auth.roles),
        ),
        usage=StorageUsageSchema(
            documents_bytes=usage.documents_bytes,
            library_bytes=usage.library_bytes,
            artifacts_bytes=usage.artifacts_bytes,
            pending_upload_bytes=usage.pending_upload_bytes,
            account_data_bytes=usage.account_data_bytes,
            total_bytes=usage.total_bytes,
        ),
        metrics=[
            StorageMetricSchema(
                key=metric.key,
                label=metric.label,
                description=metric.description,
                bytes=metric.bytes,
                record_count=metric.record_count,
                included_in_quota=metric.included_in_quota,
                measurement=metric.measurement,
                tokens=metric.tokens,
            )
            for metric in metrics
        ],
        quota_metering_note=(
            "The plan meter uses exact durable object sizes plus safe logical byte estimates "
            "for tenant-owned database content. PostgreSQL physical overhead is not claimed "
            "as exact; secret values, private content, and object keys are never returned."
        ),
        generated_at=datetime.now(UTC).isoformat(),
    )
