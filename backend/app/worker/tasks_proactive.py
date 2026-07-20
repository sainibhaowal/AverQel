import asyncio
import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.deepspace.agent_activity import AgentActivity
from app.models.deepspace.agent_todo import AgentTodo
from app.models.documents.collection_notification import CollectionNotification
from app.models.integrations.connector import Connector, ConnectorStatus
from app.models.integrations.integration import Integration
from app.repositories.documents.collection_notifications import (
    CollectionNotificationsRepository,
)
from app.services.deepspace.memory.memory_service import TodoService
from app.services.deepspace.missions.mission_registry import MissionRegistry
from app.services.deepspace.orchestration.master_orchestrator import MasterOrchestrator
from app.services.deepspace.proactive.proactive_triggers import (
    ProactiveTriggerRegistry,
)
from app.services.deepspace.proactive.trigger_runner import build_trigger_runner
from app.services.deepspace.subagents.subagent_registry import SubagentRegistry
from app.services.integrations.mcp_runtime import (
    build_mcp_runtime,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _make_trigger_runner(*, db, todo_service: TodoService):
    settings = get_settings()
    return build_trigger_runner(
        db=db,
        settings=settings,
        todo_service=todo_service,
        mission_registry_cls=MissionRegistry,
        orchestrator_cls=MasterOrchestrator,
        build_runtime=build_mcp_runtime,
        notify_proactive=_notify_proactive,
    )


def _already_processed_gmail_message(
    *,
    db,
    tenant_id,
    connector_id: str,
    message_id: str,
    window: timedelta = timedelta(days=14),
) -> bool:
    trigger = ProactiveTriggerRegistry.GMAIL_URGENT
    if window != trigger.cooldown:
        trigger = trigger.with_cooldown(window)
    return ProactiveTriggerRegistry(db).already_processed(
        trigger=trigger,
        tenant_id=tenant_id,
        connector_id=connector_id,
        external_id=message_id,
    )


def _notify_proactive(
    *,
    db,
    recipient_user_id,
    message: str,
    event_type: str = "agent_intervention",
    actor_user_id=None,
    collection_id=None,
    collection_name: str = "AverQel Proactive",
    idempotency_key: str | None = None,
) -> None:
    repo = CollectionNotificationsRepository(db)
    now = datetime.now(UTC)
    stable_key = (
        idempotency_key
        or hashlib.sha256(
            "|".join(
                [
                    str(recipient_user_id),
                    str(actor_user_id or ""),
                    str(collection_id or ""),
                    collection_name,
                    event_type,
                    message,
                ]
            ).encode("utf-8")
        ).hexdigest()
    )

    if repo.get_by_idempotency_key(idempotency_key=stable_key) is not None:
        return

    for existing in repo.list_for_user(user_id=recipient_user_id, limit=100):
        if (
            existing.collection_name == collection_name
            and existing.event_type == event_type
            and existing.message == message
            and existing.created_at is not None
            and (now - existing.created_at).total_seconds() < 30 * 60
        ):
            return

    repo.create(
        CollectionNotification(
            recipient_user_id=recipient_user_id,
            actor_user_id=actor_user_id,
            collection_id=collection_id,
            collection_name=collection_name,
            event_type=event_type,
            idempotency_key=stable_key,
            message=message,
        )
    )


def _retry_after_at(*, delay_minutes: int = 10) -> str:
    return _make_trigger_runner(
        db=SimpleNamespace(),
        todo_service=SimpleNamespace(),
    ).retry_after_at(delay_minutes=delay_minutes)


def _gmail_failure_notification_suppressed(
    *,
    db,
    tenant_id,
    failure_idempotency_key: str,
) -> bool:
    """Suppress duplicate Gmail failure alerts while the existing cooldown is still active."""
    return _make_trigger_runner(
        db=db,
        todo_service=SimpleNamespace(),
    ).failure_notification_suppressed(
        tenant_id=tenant_id,
        failure_idempotency_key=failure_idempotency_key,
    )


def _next_run_for_rule(rule: AgentTodo, *, now: datetime | None = None) -> datetime:
    return _make_trigger_runner(
        db=SimpleNamespace(),
        todo_service=SimpleNamespace(),
    ).next_run_for_rule(rule, now=now)


async def _run_recurring_rule(
    *,
    db,
    todo_service: TodoService,
    rule: AgentTodo,
    cycle_id: str | None = None,
) -> None:
    runner = _make_trigger_runner(db=db, todo_service=todo_service)
    await runner.run_recurring_rule(rule=rule, cycle_id=cycle_id)


@celery_app.task(name="app.worker.tasks_proactive.monitor_agent_triggers")
def monitor_agent_triggers() -> None:
    """
    Heartbeat task that polls for proactive agent interventions.
    Runs every 5 minutes via Celery Beat.
    """
    db = SessionLocal()

    try:
        _run_proactive_cycle(db)
    finally:
        db.close()


def _run_proactive_cycle(db) -> None:
    settings = get_settings()
    registry = SubagentRegistry()
    registry.record_daemon_heartbeat(phase="cycle_start")
    cycle_id = uuid.uuid4().hex

    try:
        # Revalidate all non-syncing connectors so paused/error connectors can
        # recover automatically when upstream services become healthy again.
        stmt = (
            select(Connector)
            .join(Integration)
            .where(Connector.status != ConnectorStatus.SYNCING)
        )
        connectors = db.execute(stmt).scalars().all()
        todo_service = TodoService(db)
        support_reports: dict[tuple[str, str], dict[str, object]] = {}

        def _support_report_for(conn: Connector) -> dict[str, object]:
            key = (str(conn.tenant_id), str(conn.user_id))
            if key in support_reports:
                return support_reports[key]

            auth = AuthContext(
                tenant_id=conn.tenant_id,
                user_id=conn.user_id,
                roles=frozenset({"user"}),
                token_id=f"proactive-support-{conn.tenant_id}-{conn.user_id}",
            )
            orchestrator = MasterOrchestrator(db=db, auth=auth, settings=settings)
            execution_mode = MissionRegistry(settings, db=db).get_execution_mode(
                tenant_id=str(conn.tenant_id),
                user_id=str(conn.user_id),
            )
            try:
                support_reports[key] = asyncio.run(
                    orchestrator.execute_support_mission(
                        execution_mode=execution_mode,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Support mission failed for tenant %s user %s; caching degraded report.",
                    conn.tenant_id,
                    conn.user_id,
                )
                support_reports[key] = {
                    "status": "degraded",
                    "healthy": False,
                    "error_code": "support_mission_failed",
                    "retryable": True,
                    "vitals": {
                        "internet": "disconnected",
                        "llm": "disconnected",
                        "web_search": "unavailable",
                        "sources": 0,
                    },
                    "connector_health": {},
                    "daemon_heartbeat": {},
                    "summary": str(exc)[:500],
                    "final_output": str(exc)[:2000],
                    "error": str(exc)[:500],
                    "fallback_mode": "degraded_support_report",
                }
            return support_reports[key]

        for conn in connectors:
            try:
                support_report = _support_report_for(conn)
                vitals = dict(support_report.get("vitals") or {})
                if (
                    vitals.get("internet") == "disconnected"
                    or vitals.get("llm") == "disconnected"
                ):
                    logger.warning(
                        f"Skipping proactive scan for tenant {conn.tenant_id} due to poor vitals: {vitals}"
                    )
                    todo_service.upsert_task(
                        tenant_id=str(conn.tenant_id),
                        user_id=str(conn.user_id),
                        content=f"Restore proactive capacity for {conn.name}",
                        active_form=f"Restore proactive capacity for {conn.name}",
                        status="pending",
                        priority=80,
                        metadata_json={
                            "source": (
                                conn.integration.slug if conn.integration else "unknown"
                            ),
                            "connector_id": str(conn.id),
                            "connector_name": conn.name,
                            "phase": "vitals",
                            "proactive_cycle_id": cycle_id,
                            "vitals": vitals,
                            "support_report_status": str(
                                support_report.get("status") or ""
                            ),
                            "support_report_error_code": str(
                                support_report.get("error_code") or ""
                            ),
                            "support_report_summary": str(
                                support_report.get("summary") or ""
                            )[:500],
                        },
                    )
                    _notify_proactive(
                        db=db,
                        recipient_user_id=conn.user_id,
                        message=f"Proactive scan paused for {conn.name} because vitals are degraded.",
                        idempotency_key=hashlib.sha256(
                            f"{conn.tenant_id}|{conn.user_id}|{conn.id}|vitals|{support_report.get('status') or ''}|{vitals.get('internet')}|{vitals.get('llm')}".encode()
                        ).hexdigest(),
                    )
                    continue
                connector_health = dict(support_report.get("connector_health") or {})
                connector_report = dict(connector_health.get(str(conn.id)) or {})
                if connector_report and not bool(connector_report.get("healthy")):
                    logger.warning(
                        "Skipping connector scan for %s due to degraded connector health: %s",
                        conn.name,
                        connector_report,
                    )
                    continue

                db.add(
                    AgentActivity(
                        tenant_id=conn.tenant_id,
                        activity_type="heartbeat",
                        description=f"Heartbeat check for {conn.name}.",
                        source=conn.integration.slug if conn.integration else "unknown",
                        metadata_json={
                            "phase": "heartbeat",
                            "connector_id": str(conn.id),
                            "connector_name": conn.name,
                            "integration_slug": (
                                conn.integration.slug if conn.integration else None
                            ),
                            "proactive_cycle_id": cycle_id,
                            "vitals": vitals,
                            "support_report": support_report,
                        },
                    )
                )
                db.commit()

                if conn.integration and conn.integration.slug != "gmail":
                    continue

                runner = _make_trigger_runner(db=db, todo_service=todo_service)
                runner.process_gmail_connector(conn=conn, cycle_id=cycle_id)

            except Exception as e:
                logger.error(f"Error in proactive scan for connector {conn.id}: {e}")
                db.rollback()

        try:
            due_pairs = db.execute(
                select(AgentTodo.tenant_id, AgentTodo.user_id)
                .where(
                    AgentTodo.enabled == 1,
                    AgentTodo.is_recurring == 1,
                    AgentTodo.next_run_at.is_not(None),
                    AgentTodo.next_run_at <= datetime.now(UTC),
                )
                .distinct()
            ).all()
            for tenant_id, user_id in due_pairs:
                todo_service = TodoService(db)
                due_rules = todo_service.list_due_recurring_tasks(
                    tenant_id=str(tenant_id), user_id=str(user_id)
                )
                for rule in due_rules:
                    retry_reference = (
                        getattr(rule, "last_run_at", None)
                        or getattr(rule, "next_run_at", None)
                        or datetime.now(UTC)
                    )
                    try:
                        asyncio.run(
                            _run_recurring_rule(
                                db=db,
                                todo_service=todo_service,
                                rule=rule,
                                cycle_id=cycle_id,
                            )
                        )
                        db.commit()
                    except Exception as e:
                        logger.error(f"Error running proactive rule {rule.id}: {e}")
                        db.rollback()
                        db.add(
                            AgentActivity(
                                tenant_id=rule.tenant_id,
                                activity_type="error",
                                description=f"Recurring proactive task failed: {rule.content}",
                                source=str(
                                    (rule.automation_json or {}).get("source")
                                    or "proactive"
                                ),
                                metadata_json={
                                    "phase": "error",
                                    "task_id": str(rule.id),
                                    "message": str(e),
                                    "retryable": True,
                                    "retry_after_at": _retry_after_at(delay_minutes=10),
                                    "retry_reference": (
                                        retry_reference.isoformat().replace(
                                            "+00:00", "Z"
                                        )
                                        if isinstance(retry_reference, datetime)
                                        else str(retry_reference)
                                    ),
                                    "proactive_cycle_id": cycle_id,
                                },
                            )
                        )
                        _notify_proactive(
                            db=db,
                            recipient_user_id=rule.user_id,
                            message=f"Recurring task failed and will retry: {rule.content}",
                            idempotency_key=hashlib.sha256(
                                f"{rule.id}|retry_failed|{retry_reference.isoformat() if isinstance(retry_reference, datetime) else retry_reference}".encode()
                            ).hexdigest(),
                        )
                        todo_service.mark_task_run(
                            task=rule,
                            next_run_at=datetime.now(UTC) + timedelta(minutes=10),
                            last_run_at=datetime.now(UTC),
                            status="pending",
                        )
                        db.commit()
        except Exception as e:
            logger.error("Recurring proactive sweep failed: %s", e)
            db.rollback()
    finally:
        registry.record_daemon_heartbeat(phase="idle")


def run_proactive_daemon() -> None:
    """
    Long-running proactive worker loop.

    This is the background daemon path for deployments that want a continuously
    running proactive coordinator instead of relying only on Celery Beat.
    """

    from app.core.config import get_settings

    settings = get_settings()
    interval = max(
        30, int(getattr(settings, "deepspace_proactive_daemon_interval_seconds", 300))
    )
    registry = SubagentRegistry(settings)
    registry.record_daemon_heartbeat(phase="starting")
    logger.info("Starting proactive daemon with %ss interval.", interval)

    while True:
        db = SessionLocal()
        try:
            _run_proactive_cycle(db)
            registry.record_daemon_heartbeat(phase="sleeping")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Proactive daemon cycle failed: %s", exc)
            registry.record_daemon_heartbeat(phase="error")
        finally:
            db.close()

        time.sleep(interval)
