"""Safe, tenant-scoped Storage retention scans and local archive proof."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.auth.models.tenant import Tenant
from app.core.config import get_settings
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app
from app.system.models.storage_lifecycle import StorageRetentionRun
from app.system.services.metrics_service import (
    STORAGE_RETENTION_ITEMS_TOTAL,
    STORAGE_RETENTION_MISMATCHES_TOTAL,
    STORAGE_RETENTION_RUNS_TOTAL,
)
from app.system.services.storage_lifecycle import StorageLifecycleService
from app.system.services.storage_lifecycle_adapters import StorageLifecycleAdapterService

logger = logging.getLogger(__name__)


@celery_app.task(name="maintenance.storage_retention_scan")  # type: ignore[misc]
def storage_retention_scan() -> dict[str, int]:
    """Reconcile and preview retention, optionally archiving safe metadata.

    Automatic archive is opt-in for local/staging only. It changes lifecycle
    metadata and creates a restore manifest; source rows and objects are never
    deleted. Production and permanent purge remain disabled by design.
    """
    settings = get_settings()
    automatic_archive = settings.storage_retention_automatic_archive_enabled and settings.env in {
        "development",
        "test",
        "staging",
    }
    session = get_session_factory()()
    tenants_scanned = 0
    candidates = 0
    protected = 0
    reconciliations = 0
    mismatches = 0
    archived = 0
    archive_blocked_by_mismatch = 0
    try:
        session.execute(text("SET ROLE aks_app"))
        tenant_ids = [row[0] for row in session.query(Tenant.id).all()]
        for tenant_id in tenant_ids:
            scan_service = StorageLifecycleService(session)
            scan_run = scan_service.claim_scan_run(tenant_id=tenant_id)
            if scan_run is None:
                # Another worker owns this tenant lease. It will either
                # finish or become reclaimable after the lease expires.
                continue
            scan_run_id = scan_run.id
            reconciliation = StorageLifecycleAdapterService(session).reconcile_tenant(
                tenant_id=tenant_id
            )
            reconciliations += 1
            mismatches += reconciliation.mismatch_count
            STORAGE_RETENTION_MISMATCHES_TOTAL.inc(reconciliation.mismatch_count)
            STORAGE_RETENTION_RUNS_TOTAL.labels("reconciliation", reconciliation.status).inc()
            scan_service.advance_scan_run(
                tenant_id=tenant_id, run_id=scan_run_id, cursor="reconciled"
            )
            preview = StorageLifecycleService(session).preview(tenant_id=tenant_id)
            tenants_scanned += 1
            candidates += preview.candidate_count
            protected += preview.protected_count
            STORAGE_RETENTION_RUNS_TOTAL.labels("preview", "complete").inc()
            STORAGE_RETENTION_ITEMS_TOTAL.labels("candidate").inc(preview.candidate_count)
            STORAGE_RETENTION_ITEMS_TOTAL.labels("protected").inc(preview.protected_count)
            scan_service.advance_scan_run(
                tenant_id=tenant_id, run_id=scan_run_id, cursor="previewed"
            )
            if (
                automatic_archive
                and preview.run_id is not None
                and reconciliation.mismatch_count == 0
            ):
                # ``preview`` commits, so its transaction-local RLS context
                # must be restored before reading the preview run.
                set_db_tenant_context(session, tenant_id)
                preview_run = session.get(StorageRetentionRun, preview.run_id)
                archive_run = StorageRetentionRun(
                    tenant_id=tenant_id,
                    policy_version=preview_run.policy_version if preview_run else 1,
                    retention_mode=preview.mode,
                    retention_days=preview.days,
                    status="running",
                    operation="archive",
                )
                session.add(archive_run)
                session.flush()
                archived_for_tenant = StorageLifecycleService(session).archive_eligible_items(
                    tenant_id=tenant_id,
                    policy_version=archive_run.policy_version,
                    run_id=archive_run.id,
                )
                archive_run.candidate_count = archived_for_tenant
                archive_run.status = "complete"
                archive_run.completed_at = datetime.now(UTC)
                archived += archived_for_tenant
                STORAGE_RETENTION_RUNS_TOTAL.labels("archive", "complete").inc()
                STORAGE_RETENTION_ITEMS_TOTAL.labels("archived").inc(archived_for_tenant)
                session.commit()
            elif automatic_archive and reconciliation.mismatch_count:
                archive_blocked_by_mismatch += 1
            scan_service.complete_scan_run(
                tenant_id=tenant_id,
                run_id=scan_run_id,
                candidate_count=preview.candidate_count,
                protected_count=preview.protected_count,
            )
        return {
            "tenants_scanned": tenants_scanned,
            "candidates": candidates,
            "protected": protected,
            "reconciliations": reconciliations,
            "reconciliation_mismatches": mismatches,
            "archived": archived,
            "archive_blocked_by_mismatch": archive_blocked_by_mismatch,
            "source_rows_deleted": 0,
        }
    except Exception:
        session.rollback()
        logger.exception("Storage retention scan failed; no source data was changed.")
        raise
    finally:
        try:
            session.execute(text("RESET ROLE"))
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        session.close()
