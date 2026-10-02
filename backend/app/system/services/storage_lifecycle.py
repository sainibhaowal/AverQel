from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, exists, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.deepspace.models.agent_runtime import DeepSpaceAgentRun, DeepSpaceRunEvent
from app.deepspace.models.artifact_job import DeepSpaceArtifactJob
from app.deepspace.models.library_upload import DeepSpaceLibraryUpload
from app.deepspace.models.media_artifact import DeepSpaceMediaArtifact
from app.deepspace.models.queue_control import DeepSpaceQueueControl
from app.deepspace.models.queued_turn import DeepSpaceQueuedTurn
from app.deepspace.models.schedule import DeepSpaceSchedule
from app.platform.database.session import set_db_tenant_context
from app.system.models.storage_lifecycle import (
    StorageArchiveManifest,
    StorageLifecycleItem,
    StorageRetentionDecision,
    StorageRetentionRun,
)
from app.system.models.tenant_storage_allocation import TenantStorageAllocation
from app.system.services.storage_quota import StorageQuotaService

RETENTION_DAYS_BY_MODE: dict[str, int] = {"off": 0, "30": 30, "60": 60, "90": 90}
PROTECTED_CATEGORIES = {"provider_settings", "security", "audit"}
USER_CONTENT_CATEGORIES = {
    "files",
    "library",
    "artifacts",
    "chat_history",
    "memory",
    "queries",
    "collections",
    "queues",
}
PROTECTED_RUN_STATUSES = {
    "running",
    "cancelling",
    "awaiting_approval",
    "awaiting_user",
    "blocked",
    "failed",
}
PROTECTED_QUEUE_STATUSES = {"queued", "running", "stopping", "failed"}


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    mode: str
    days: int
    version: int


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    run_id: uuid.UUID | None
    mode: str
    days: int
    cutoff: datetime | None
    candidate_count: int
    candidate_bytes: int
    protected_count: int
    legacy_data_preserved: bool


class StorageLifecycleService:
    """Tenant-scoped, archive-first retention metadata service.

    Archive changes lifecycle metadata and creates a restore manifest. It
    never deletes source rows or objects. Unknown data is protected whenever
    this service cannot prove it is safe.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def policy(self, *, tenant_id: uuid.UUID) -> RetentionPolicy:
        allocation = self.db.execute(
            select(TenantStorageAllocation).where(TenantStorageAllocation.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if allocation is None:
            return RetentionPolicy(mode="off", days=0, version=1)
        mode = (
            allocation.retention_mode
            if allocation.retention_mode in RETENTION_DAYS_BY_MODE
            else "off"
        )
        days = RETENTION_DAYS_BY_MODE[mode]
        return RetentionPolicy(
            mode=mode, days=days, version=max(1, allocation.retention_policy_version)
        )

    def set_policy(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        mode: str,
    ) -> RetentionPolicy:
        normalized = str(mode).strip().lower()
        if normalized not in RETENTION_DAYS_BY_MODE:
            raise ValueError("Retention must be Off, 30, 60, or 90 days.")
        set_db_tenant_context(self.db, tenant_id)
        requested_plan = StorageQuotaService(self.db).plan_for_user(
            tenant_id=tenant_id, user_id=user_id
        )
        allocation = StorageQuotaService(self.db).ensure_allocation(
            tenant_id=tenant_id, requested_plan=requested_plan
        )
        allocation.retention_mode = normalized
        allocation.retention_days = RETENTION_DAYS_BY_MODE[normalized]
        allocation.retention_policy_version = (
            max(1, int(allocation.retention_policy_version or 1)) + 1
        )
        allocation.retention_updated_at = datetime.now(UTC)
        self.db.commit()
        return self.policy(tenant_id=tenant_id)

    def claim_scan_run(
        self,
        *,
        tenant_id: uuid.UUID,
        lease_minutes: int = 15,
    ) -> StorageRetentionRun | None:
        """Claim one tenant scan, recovering only an expired lease.

        The claim is committed before source reconciliation starts. If a
        worker disappears, a later scan can safely reclaim the same tenant
        after the lease expires without duplicating active work.
        """
        now = datetime.now(UTC)
        set_db_tenant_context(self.db, tenant_id)
        run = (
            self.db.execute(
                select(StorageRetentionRun)
                .where(
                    StorageRetentionRun.tenant_id == tenant_id,
                    StorageRetentionRun.operation == "scan",
                    StorageRetentionRun.status == "running",
                )
                .order_by(StorageRetentionRun.started_at.desc())
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .first()
        )
        if run is not None and run.lease_until is not None and run.lease_until > now:
            self.db.rollback()
            return None
        policy = self.policy(tenant_id=tenant_id)
        if run is None:
            run = StorageRetentionRun(
                tenant_id=tenant_id,
                policy_version=policy.version,
                retention_mode=policy.mode,
                retention_days=policy.days,
                status="running",
                operation="scan",
                checkpoint_cursor="start",
                started_at=now,
            )
            self.db.add(run)
        else:
            run.policy_version = policy.version
            run.retention_mode = policy.mode
            run.retention_days = policy.days
            run.error_message = None
        run.lease_until = now + timedelta(minutes=max(1, lease_minutes))
        self.db.flush()
        self.db.commit()
        return run

    def advance_scan_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        cursor: str,
    ) -> None:
        set_db_tenant_context(self.db, tenant_id)
        run = self.db.execute(
            select(StorageRetentionRun)
            .where(
                StorageRetentionRun.id == run_id,
                StorageRetentionRun.tenant_id == tenant_id,
                StorageRetentionRun.operation == "scan",
                StorageRetentionRun.status == "running",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise ValueError("Retention scan lease is no longer owned.")
        run.checkpoint_cursor = cursor[:255]
        run.lease_until = datetime.now(UTC) + timedelta(minutes=15)
        self.db.commit()

    def complete_scan_run(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        candidate_count: int,
        protected_count: int,
    ) -> None:
        set_db_tenant_context(self.db, tenant_id)
        run = self.db.execute(
            select(StorageRetentionRun)
            .where(StorageRetentionRun.id == run_id, StorageRetentionRun.tenant_id == tenant_id)
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            return
        run.checkpoint_cursor = "complete"
        run.candidate_count = candidate_count
        run.protected_count = protected_count
        run.status = "complete"
        run.lease_until = None
        run.completed_at = datetime.now(UTC)
        self.db.commit()

    def record_activity(
        self,
        *,
        tenant_id: uuid.UUID,
        category: str,
        source_type: str,
        source_id: str,
        activity_kind: str,
        size_bytes: int = 0,
        owner_user_id: uuid.UUID | None = None,
        dependency_group_id: str | None = None,
        protected_until: datetime | None = None,
        protection_reason: str | None = None,
        at: datetime | None = None,
        replace_size: bool = False,
    ) -> StorageLifecycleItem:
        """Upsert identity/activity metadata without copying user content."""
        now = at or datetime.now(UTC)
        set_db_tenant_context(self.db, tenant_id)
        source_key = str(source_id)
        values = {
            "tenant_id": tenant_id,
            "owner_user_id": owner_user_id,
            "category": category,
            "source_type": source_type,
            "source_id": source_key,
            "state": "active",
            "size_bytes": max(0, int(size_bytes)),
            "last_meaningful_activity_at": now,
            "last_activity_kind": activity_kind,
            "dependency_group_id": dependency_group_id,
            "protected_until": protected_until,
            "protection_reason": protection_reason,
            "policy_version": 1,
            "updated_at": now,
        }
        statement = pg_insert(StorageLifecycleItem).values(**values)
        excluded = statement.excluded
        existing = StorageLifecycleItem
        statement = statement.on_conflict_do_update(
            index_elements=[
                "tenant_id",
                "category",
                "source_type",
                "source_id",
            ],
            set_={
                "owner_user_id": func.coalesce(excluded.owner_user_id, existing.owner_user_id),
                "size_bytes": (
                    excluded.size_bytes
                    if replace_size
                    else func.greatest(existing.size_bytes, excluded.size_bytes)
                ),
                "last_meaningful_activity_at": func.greatest(
                    existing.last_meaningful_activity_at,
                    excluded.last_meaningful_activity_at,
                ),
                "last_activity_kind": case(
                    (
                        excluded.last_meaningful_activity_at
                        >= existing.last_meaningful_activity_at,
                        excluded.last_activity_kind,
                    ),
                    else_=existing.last_activity_kind,
                ),
                "dependency_group_id": func.coalesce(
                    excluded.dependency_group_id, existing.dependency_group_id
                ),
                "protected_until": func.coalesce(
                    excluded.protected_until, existing.protected_until
                ),
                "protection_reason": func.coalesce(
                    excluded.protection_reason, existing.protection_reason
                ),
                # Reconciliation observes source rows; it is not meaningful
                # user activity and must not silently undo an archive.
                "state": case(
                    (excluded.last_activity_kind == "reconciliation", existing.state),
                    else_="active",
                ),
                "archived_at": None,
                "purge_after": None,
                "updated_at": now,
            },
        )
        self.db.execute(statement)
        self.db.flush()
        return self.db.execute(
            select(StorageLifecycleItem).where(
                StorageLifecycleItem.tenant_id == tenant_id,
                StorageLifecycleItem.category == category,
                StorageLifecycleItem.source_type == source_type,
                StorageLifecycleItem.source_id == source_key,
            )
        ).scalar_one()

    def touch_source(
        self,
        *,
        tenant_id: uuid.UUID,
        category: str,
        source_type: str,
        source_id: str,
        owner_user_id: uuid.UUID | None = None,
        dependency_group_id: str | None = None,
        activity_kind: str = "source_write",
    ) -> StorageLifecycleItem:
        """Record a direct durable write without copying source payloads.

        This deliberately does not recalculate the source size. Quota services
        remain responsible for capacity enforcement and reconciliation remains
        the authoritative size repair path. A direct touch only prevents a
        newly written or edited source from being mistaken for inactive before
        the next reconciliation pass.
        """
        return self.record_activity(
            tenant_id=tenant_id,
            category=category,
            source_type=source_type,
            source_id=str(source_id),
            owner_user_id=owner_user_id,
            dependency_group_id=dependency_group_id,
            activity_kind=activity_kind,
        )

    def preview(self, *, tenant_id: uuid.UUID) -> RetentionPreview:
        policy = self.policy(tenant_id=tenant_id)
        if policy.days <= 0:
            return RetentionPreview(
                run_id=None,
                mode="off",
                days=0,
                cutoff=None,
                candidate_count=0,
                candidate_bytes=0,
                protected_count=0,
                legacy_data_preserved=True,
            )

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=policy.days)
        set_db_tenant_context(self.db, tenant_id)
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"storage-retention-preview:{tenant_id}"},
        )
        items = list(
            self.db.execute(
                select(StorageLifecycleItem)
                .where(
                    StorageLifecycleItem.tenant_id == tenant_id,
                    StorageLifecycleItem.state.in_(("active", "eligible")),
                    StorageLifecycleItem.last_meaningful_activity_at <= cutoff,
                )
                .order_by(StorageLifecycleItem.last_meaningful_activity_at.asc())
            )
            .scalars()
            .all()
        )
        run = StorageRetentionRun(
            tenant_id=tenant_id,
            policy_version=policy.version,
            retention_mode=policy.mode,
            retention_days=policy.days,
            status="preview",
            operation="preview",
            started_at=now,
            lease_until=now + timedelta(minutes=15),
        )
        self.db.add(run)
        self.db.flush()

        candidates = 0
        candidate_bytes = 0
        protected = 0
        for item in items:
            reason = self._protection_reason(item=item, tenant_id=tenant_id, now=now)
            action = "protected" if reason else "candidate"
            decision = StorageRetentionDecision(
                run_id=run.id,
                tenant_id=tenant_id,
                lifecycle_item_id=item.id,
                action=action,
                reason=reason or "inactive_threshold_reached",
                policy_version=policy.version,
            )
            self.db.add(decision)
            if reason:
                protected += 1
                item.protection_reason = reason
            else:
                candidates += 1
                candidate_bytes += max(0, int(item.size_bytes))
                item.state = "eligible"
        run.candidate_count = candidates
        run.protected_count = protected
        run.legacy_count = 0
        run.status = "preview"
        run.completed_at = datetime.now(UTC)
        self.db.commit()
        return RetentionPreview(
            run_id=run.id,
            mode=policy.mode,
            days=policy.days,
            cutoff=cutoff,
            candidate_count=candidates,
            candidate_bytes=candidate_bytes,
            protected_count=protected,
            legacy_data_preserved=True,
        )

    def archive_item(
        self,
        *,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        is_admin: bool = False,
    ) -> StorageArchiveManifest:
        """Archive one already-eligible item without touching source data."""
        set_db_tenant_context(self.db, tenant_id)
        item = self.db.execute(
            select(StorageLifecycleItem)
            .where(StorageLifecycleItem.id == item_id, StorageLifecycleItem.tenant_id == tenant_id)
            .with_for_update()
        ).scalar_one_or_none()
        if item is None:
            raise ValueError("Storage item was not found.")
        if not is_admin and item.owner_user_id != user_id:
            raise ValueError("Storage item is not owned by this user.")
        if item.state != "eligible":
            raise ValueError("Only a preview-eligible item can be archived.")
        reason = self._protection_reason(item=item, tenant_id=tenant_id, now=datetime.now(UTC))
        if reason:
            raise ValueError(f"Storage item is protected: {reason}.")
        manifest = self.db.execute(
            select(StorageArchiveManifest)
            .where(
                StorageArchiveManifest.tenant_id == tenant_id,
                StorageArchiveManifest.lifecycle_item_id == item.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if manifest is None:
            manifest = StorageArchiveManifest(
                tenant_id=tenant_id,
                lifecycle_item_id=item.id,
                category=item.category,
                source_type=item.source_type,
                source_id=item.source_id,
                state="archived",
                policy_version=item.policy_version,
                archived_at=now,
            )
            self.db.add(manifest)
        else:
            manifest.state = "archived"
            manifest.archived_at = manifest.archived_at or now
            manifest.restored_at = None
        item.state = "archived"
        item.archived_at = now
        item.updated_at = now
        self.db.flush()
        return manifest

    def archive_eligible_items(
        self,
        *,
        tenant_id: uuid.UUID,
        policy_version: int,
        run_id: uuid.UUID,
        limit: int = 500,
    ) -> int:
        """Archive eligible user-content metadata without touching source data.

        This is an internal worker operation. It is deliberately limited to
        known user-content categories; provider/security/audit and unknown
        categories remain protected by default.
        """
        set_db_tenant_context(self.db, tenant_id)
        now = datetime.now(UTC)
        items = list(
            self.db.execute(
                select(StorageLifecycleItem)
                .where(
                    StorageLifecycleItem.tenant_id == tenant_id,
                    StorageLifecycleItem.state == "eligible",
                    StorageLifecycleItem.category.in_(USER_CONTENT_CATEGORIES),
                )
                .order_by(StorageLifecycleItem.last_meaningful_activity_at.asc())
                .limit(max(1, min(limit, 5000)))
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        archived = 0
        for item in items:
            reason = self._protection_reason(item=item, tenant_id=tenant_id, now=now)
            if reason:
                item.protection_reason = reason
                continue
            manifest = self.db.execute(
                select(StorageArchiveManifest)
                .where(
                    StorageArchiveManifest.tenant_id == tenant_id,
                    StorageArchiveManifest.lifecycle_item_id == item.id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if manifest is None:
                manifest = StorageArchiveManifest(
                    tenant_id=tenant_id,
                    lifecycle_item_id=item.id,
                    category=item.category,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    state="archived",
                    policy_version=policy_version,
                    archived_at=now,
                )
                self.db.add(manifest)
            else:
                manifest.state = "archived"
                manifest.policy_version = policy_version
                manifest.archived_at = manifest.archived_at or now
                manifest.restored_at = None
            item.state = "archived"
            item.archived_at = now
            item.updated_at = now
            self.db.add(
                StorageRetentionDecision(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    lifecycle_item_id=item.id,
                    action="archived",
                    reason="inactive_threshold_reached",
                    policy_version=policy_version,
                )
            )
            archived += 1
        self.db.flush()
        return archived

    def restore_item(
        self,
        *,
        tenant_id: uuid.UUID,
        item_id: uuid.UUID,
        user_id: uuid.UUID,
        is_admin: bool = False,
    ) -> StorageArchiveManifest:
        """Restore lifecycle state idempotently; source data was never removed."""
        set_db_tenant_context(self.db, tenant_id)
        manifest = self.db.execute(
            select(StorageArchiveManifest)
            .where(
                StorageArchiveManifest.tenant_id == tenant_id,
                StorageArchiveManifest.lifecycle_item_id == item_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if manifest is None:
            raise ValueError("Archived storage item was not found.")
        item = self.db.execute(
            select(StorageLifecycleItem)
            .where(StorageLifecycleItem.id == item_id, StorageLifecycleItem.tenant_id == tenant_id)
            .with_for_update()
        ).scalar_one()
        if not is_admin and item.owner_user_id != user_id:
            raise ValueError("Storage item is not owned by this user.")
        now = datetime.now(UTC)
        item.state = "active"
        item.archived_at = None
        item.purge_after = None
        item.last_meaningful_activity_at = now
        item.last_activity_kind = "restore"
        item.updated_at = now
        manifest.state = "restored"
        manifest.restored_at = now
        self.db.flush()
        return manifest

    def set_source_protection(
        self,
        *,
        tenant_id: uuid.UUID,
        category: str,
        source_type: str,
        source_id: str,
        pinned: bool | None = None,
        legal_hold: bool | None = None,
        admin_exempt: bool | None = None,
        reason: str | None = None,
    ) -> StorageLifecycleItem:
        """Set explicit retention protections for one known tenant item."""
        set_db_tenant_context(self.db, tenant_id)
        item = self.db.execute(
            select(StorageLifecycleItem)
            .where(
                StorageLifecycleItem.tenant_id == tenant_id,
                StorageLifecycleItem.category == category,
                StorageLifecycleItem.source_type == source_type,
                StorageLifecycleItem.source_id == str(source_id),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if item is None:
            raise ValueError("Storage lifecycle item was not found.")
        if pinned is not None:
            item.pinned = bool(pinned)
        if legal_hold is not None:
            item.legal_hold = bool(legal_hold)
        if admin_exempt is not None:
            item.admin_exempt = bool(admin_exempt)
        if reason is not None:
            item.protection_reason = reason.strip()[:2000] or None
        item.updated_at = datetime.now(UTC)
        self.db.flush()
        return item

    def _protection_reason(
        self, *, item: StorageLifecycleItem, tenant_id: uuid.UUID, now: datetime
    ) -> str | None:
        if item.category in PROTECTED_CATEGORIES:
            return "protected_category"
        if item.category not in USER_CONTENT_CATEGORIES:
            return "unclassified_category"
        if item.legal_hold:
            return "legal_hold"
        if item.pinned:
            return "pinned"
        if item.admin_exempt:
            return "administrator_retention_exemption"
        if item.protected_until is not None and item.protected_until >= now:
            return "explicit_protection_window"
        if item.dependency_group_id:
            newer_dependency = self.db.execute(
                select(
                    exists().where(
                        StorageLifecycleItem.tenant_id == tenant_id,
                        StorageLifecycleItem.dependency_group_id == item.dependency_group_id,
                        StorageLifecycleItem.last_meaningful_activity_at
                        > item.last_meaningful_activity_at,
                    )
                )
            ).scalar()
            if newer_dependency:
                return "newer_dependency_in_group"

        conversation_id: uuid.UUID | None = None
        if item.source_type == "conversation":
            try:
                conversation_id = uuid.UUID(item.source_id)
            except ValueError:
                return "unparseable_source_identity"
        if conversation_id is None:
            return None

        # Events created before run_id existed cannot be proven terminal. Keep
        # them rather than guessing that an old reconnectable run is safe.
        unresolved_event = self.db.execute(
            select(
                exists().where(
                    DeepSpaceRunEvent.tenant_id == tenant_id,
                    DeepSpaceRunEvent.conversation_id == conversation_id,
                    DeepSpaceRunEvent.run_id.is_(None),
                )
            )
        ).scalar()
        if unresolved_event:
            return "unresolved_legacy_run_event"

        linked_active_event = self.db.execute(
            select(
                exists().where(
                    DeepSpaceRunEvent.tenant_id == tenant_id,
                    DeepSpaceRunEvent.conversation_id == conversation_id,
                    DeepSpaceRunEvent.run_id == DeepSpaceAgentRun.id,
                    DeepSpaceAgentRun.status.in_(PROTECTED_RUN_STATUSES),
                )
            )
        ).scalar()
        if linked_active_event:
            return "active_linked_run_event"

        active_run = self.db.execute(
            select(
                exists().where(
                    DeepSpaceAgentRun.tenant_id == tenant_id,
                    DeepSpaceAgentRun.conversation_id == conversation_id,
                    DeepSpaceAgentRun.status.in_(PROTECTED_RUN_STATUSES),
                )
            )
        ).scalar()
        if active_run:
            return "active_or_waiting_deepspace_run"

        active_queue = self.db.execute(
            select(
                exists().where(
                    DeepSpaceQueuedTurn.tenant_id == tenant_id,
                    DeepSpaceQueuedTurn.conversation_id == conversation_id,
                    DeepSpaceQueuedTurn.status.in_(PROTECTED_QUEUE_STATUSES),
                )
            )
        ).scalar()
        if active_queue:
            return "queued_or_retryable_turn"

        paused_queue = self.db.execute(
            select(
                exists().where(
                    DeepSpaceQueueControl.tenant_id == tenant_id,
                    DeepSpaceQueueControl.conversation_id == conversation_id,
                    DeepSpaceQueueControl.paused.is_(True),
                )
            )
        ).scalar()
        if paused_queue:
            return "paused_queue"

        active_upload = self.db.execute(
            select(
                exists().where(
                    DeepSpaceLibraryUpload.tenant_id == tenant_id,
                    DeepSpaceLibraryUpload.conversation_id == conversation_id,
                    DeepSpaceLibraryUpload.status.in_(
                        ("pending", "uploading", "processing", "queued")
                    ),
                )
            )
        ).scalar()
        if active_upload:
            return "active_upload"

        active_artifact_job = self.db.execute(
            select(
                exists().where(
                    DeepSpaceArtifactJob.tenant_id == tenant_id,
                    DeepSpaceArtifactJob.conversation_id == conversation_id,
                    DeepSpaceArtifactJob.status.in_(("queued", "running", "processing")),
                )
            )
        ).scalar()
        if active_artifact_job:
            return "active_artifact_job"

        referenced_artifact = self.db.execute(
            select(
                exists().where(
                    DeepSpaceMediaArtifact.tenant_id == tenant_id,
                    DeepSpaceMediaArtifact.conversation_id == conversation_id,
                    DeepSpaceMediaArtifact.status != "deleted",
                )
            )
        ).scalar()
        if referenced_artifact:
            return "referenced_artifact"

        active_schedule = self.db.execute(
            select(
                exists().where(
                    DeepSpaceSchedule.tenant_id == tenant_id,
                    DeepSpaceSchedule.conversation_id == conversation_id,
                    DeepSpaceSchedule.status == "active",
                )
            )
        ).scalar()
        if active_schedule:
            return "active_schedule"
        return None
