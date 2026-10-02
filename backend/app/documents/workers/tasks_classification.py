from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.ids import generate_uuid7_with_fallback
from app.documents.models.organization import (
    DocumentAutomationSchedule,
    DocumentAutomationScheduleRule,
    DocumentAutomationScheduleRun,
    DocumentClassificationRule,
    DocumentClassificationRun,
)
from app.documents.services.classification_service import ClassificationService
from app.documents.services.schedule_service import next_schedule_run
from app.platform.database.session import get_session_factory, set_db_tenant_context
from app.platform.worker.celery_app import celery_app


def _selected_enabled_rules(
    session, schedule: DocumentAutomationSchedule
) -> list[DocumentClassificationRule]:
    selected_ids = (
        session.query(DocumentAutomationScheduleRule.rule_id)
        .filter(
            DocumentAutomationScheduleRule.tenant_id == schedule.tenant_id,
            DocumentAutomationScheduleRule.schedule_id == schedule.id,
        )
        .all()
    )
    query = session.query(DocumentClassificationRule).filter(
        DocumentClassificationRule.tenant_id == schedule.tenant_id,
        DocumentClassificationRule.enabled.is_(True),
    )
    if selected_ids:
        query = query.filter(
            DocumentClassificationRule.id.in_([rule_id for rule_id, in selected_ids])
        )
    return query.order_by(
        DocumentClassificationRule.priority.asc(),
        DocumentClassificationRule.created_at.asc(),
    ).all()


def _fail_schedule_run(session, run: DocumentAutomationScheduleRun, message: str) -> None:
    run.status = "failed"
    run.error_message = message[:2000]
    run.completed_at = datetime.now(UTC)
    session.commit()


def _execute_schedule_run(
    session,
    *,
    run: DocumentAutomationScheduleRun,
    schedule: DocumentAutomationSchedule,
    advance_schedule: bool,
) -> DocumentAutomationScheduleRun:
    run.status = "running"
    run.started_at = datetime.now(UTC)
    session.commit()
    try:
        rules = _selected_enabled_rules(session, schedule)
        if not rules:
            run.error_message = "No enabled classification rules are selected for this schedule."
        service = ClassificationService(db=session)
        for rule in rules:
            child_run = DocumentClassificationRun(
                id=generate_uuid7_with_fallback(),
                tenant_id=schedule.tenant_id,
                rule_id=rule.id,
                actor_user_id=run.actor_user_id,
                source="schedule" if run.source == "schedule" else "manual",
                status="queued",
            )
            session.add(child_run)
            session.commit()
            completed = service.run_rule(run=child_run, rule=rule)
            run.scanned_count += completed.scanned_count
            run.matched_count += completed.matched_count
            run.applied_count += completed.applied_count
            run.failed_count += completed.failed_count
        run.status = "completed" if run.failed_count == 0 else "completed_with_errors"
        schedule.last_run_at = datetime.now(UTC)
        if advance_schedule:
            schedule.next_run_at = next_schedule_run(schedule)
    except Exception as exc:
        session.rollback()
        refreshed = session.get(DocumentAutomationScheduleRun, run.id)
        if refreshed is None:
            raise
        run = refreshed
        run.status = "failed"
        run.error_message = str(exc)[:2000]
    run.completed_at = datetime.now(UTC)
    session.commit()
    return run


@celery_app.task(name="documents.run_automation_schedule")
def run_automation_schedule_task(run_id: str, tenant_id: str) -> dict[str, object]:
    session = get_session_factory()()
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        run_uuid = uuid.UUID(run_id)
        set_db_tenant_context(session, tenant_uuid)
        run = (
            session.query(DocumentAutomationScheduleRun)
            .filter(
                DocumentAutomationScheduleRun.id == run_uuid,
                DocumentAutomationScheduleRun.tenant_id == tenant_uuid,
            )
            .one_or_none()
        )
        if run is None or run.schedule_id is None:
            return {"status": "missing"}
        schedule = (
            session.query(DocumentAutomationSchedule)
            .filter(
                DocumentAutomationSchedule.id == run.schedule_id,
                DocumentAutomationSchedule.tenant_id == tenant_uuid,
            )
            .one_or_none()
        )
        if schedule is None:
            _fail_schedule_run(session, run, "The schedule was deleted before the run started.")
            return {"status": run.status}
        completed = _execute_schedule_run(
            session,
            run=run,
            schedule=schedule,
            advance_schedule=run.source == "schedule",
        )
        return {
            "status": completed.status,
            "matched_count": completed.matched_count,
            "applied_count": completed.applied_count,
            "failed_count": completed.failed_count,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@celery_app.task(name="documents.run_classification_rule")
def run_classification_rule_task(run_id: str, tenant_id: str) -> dict[str, object]:
    """Compatibility task for direct manual rule runs."""
    session = get_session_factory()()
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        run_uuid = uuid.UUID(run_id)
        set_db_tenant_context(session, tenant_uuid)
        run = (
            session.query(DocumentClassificationRun)
            .filter(
                DocumentClassificationRun.id == run_uuid,
                DocumentClassificationRun.tenant_id == tenant_uuid,
            )
            .one_or_none()
        )
        if run is None:
            return {"status": "missing"}
        if run.rule_id is None:
            run.status = "failed"
            run.error_message = "The rule was deleted before the run started."
            run.completed_at = datetime.now(UTC)
            session.commit()
            return {"status": run.status}
        rule = (
            session.query(DocumentClassificationRule)
            .filter(
                DocumentClassificationRule.id == run.rule_id,
                DocumentClassificationRule.tenant_id == tenant_uuid,
            )
            .one_or_none()
        )
        if rule is None:
            run.status = "failed"
            run.error_message = "The rule was deleted before the run started."
            run.completed_at = datetime.now(UTC)
            session.commit()
            return {"status": run.status}
        completed = ClassificationService(db=session).run_rule(run=run, rule=rule)
        return {
            "status": completed.status,
            "matched_count": completed.matched_count,
            "applied_count": completed.applied_count,
            "failed_count": completed.failed_count,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@celery_app.task(name="documents.apply_classification_schedules")
def apply_classification_schedules() -> int:
    session = get_session_factory()()
    now = datetime.now(UTC)
    queued = 0
    try:
        schedules = (
            session.query(DocumentAutomationSchedule)
            .filter(
                DocumentAutomationSchedule.enabled.is_(True),
                (
                    DocumentAutomationSchedule.next_run_at.is_(None)
                    | (DocumentAutomationSchedule.next_run_at <= now)
                ),
            )
            .with_for_update(skip_locked=True)
            .limit(100)
            .all()
        )
        for schedule in schedules:
            set_db_tenant_context(session, schedule.tenant_id)
            # Reserve the next slot before processing so a slow run cannot be
            # picked up again by the next five-minute dispatcher tick.
            schedule.next_run_at = next_schedule_run(schedule, now=now)
            run = DocumentAutomationScheduleRun(
                id=generate_uuid7_with_fallback(),
                tenant_id=schedule.tenant_id,
                schedule_id=schedule.id,
                schedule_name=schedule.name,
                actor_user_id=schedule.created_by_user_id,
                source="schedule",
                status="queued",
            )
            session.add(run)
            session.commit()
            _execute_schedule_run(session, run=run, schedule=schedule, advance_schedule=False)
            queued += 1
        return queued
    finally:
        session.close()
