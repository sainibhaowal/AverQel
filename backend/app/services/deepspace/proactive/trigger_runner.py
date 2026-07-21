from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.auth.dependencies import AuthContext
from app.models.deepspace.agent_activity import AgentActivity
from app.models.deepspace.agent_todo import AgentTodo
from app.integrations.models.connector import Connector
from app.integrations.models.integration import Integration
from app.services.deepspace.proactive.proactive_triggers import (
    ProactiveTrigger,
    ProactiveTriggerRegistry,
)
from app.services.deepspace.proactive.trigger_contracts import (
    GmailTriggerCandidate,
    RecurringRuleRunResult,
    TriggerActivityRecord,
    TriggerNotificationRecord,
    TriggerTodoRecord,
)

logger = logging.getLogger(__name__)


class TriggerRunner:
    """Shared lifecycle runner for recurring rules and proactive trigger scans."""

    def __init__(
        self,
        *,
        db,
        settings,
        todo_service,
        mission_registry_cls,
        orchestrator_cls,
        build_runtime: Callable[[dict[str, Any]], Any],
        notify_proactive: Callable[..., None],
    ) -> None:
        self.db = db
        self.settings = settings
        self.todo_service = todo_service
        self.mission_registry_cls = mission_registry_cls
        self.orchestrator_cls = orchestrator_cls
        self.build_runtime = build_runtime
        self.notify_proactive = notify_proactive
        self.trigger_registry = ProactiveTriggerRegistry(db)

    def next_run_for_rule(
        self,
        rule: AgentTodo,
        *,
        now: datetime | None = None,
    ) -> datetime:
        now = now or datetime.now(UTC)
        automation = dict(rule.automation_json or {})
        schedule_type = str(automation.get("schedule_type") or "daily").lower()
        if schedule_type == "interval":
            interval_minutes = int(automation.get("interval_minutes") or 1440)
            return now + timedelta(minutes=max(interval_minutes, 1))
        if schedule_type == "daily":
            return now + timedelta(days=1)
        if schedule_type == "weekly":
            return now + timedelta(days=7)
        return now + timedelta(days=1)

    async def run_recurring_rule(
        self,
        *,
        rule: AgentTodo,
        cycle_id: str | None = None,
    ) -> RecurringRuleRunResult:
        automation = dict(rule.automation_json or {})
        auth = AuthContext(
            tenant_id=rule.tenant_id,
            user_id=rule.user_id,
            roles=frozenset({"user"}),
            token_id=f"proactive-{rule.id}",
        )

        action_type = str(automation.get("action_type") or "agent_prompt").lower()
        last_run_at = getattr(rule, "last_run_at", None)
        next_run_at = getattr(rule, "next_run_at", None)
        run_marker = (
            last_run_at.isoformat().replace("+00:00", "Z")
            if last_run_at is not None
            else (
                next_run_at.isoformat().replace("+00:00", "Z")
                if next_run_at
                else str(rule.id)
            )
        )
        now = datetime.now(UTC)
        next_run = self.next_run_for_rule(rule, now=now)

        if automation.get("requires_approval") or action_type in {
            "destructive",
            "delete",
        }:
            activity = TriggerActivityRecord(
                activity_type="approval",
                description=f"Recurring rule requires approval: {rule.content}",
                source=str(automation.get("source") or "proactive"),
                metadata_json={
                    "phase": "approval",
                    "task_id": str(rule.id),
                    "schedule_type": automation.get("schedule_type"),
                    "proactive_cycle_id": cycle_id,
                    "automation_json": automation,
                },
            )
            notification = TriggerNotificationRecord(
                recipient_user_id=rule.user_id,
                message=f"Recurring rule needs approval: {rule.content}",
                idempotency_key=hashlib.sha256(
                    f"{rule.id}|approval|{run_marker}".encode()
                ).hexdigest(),
            )
            self._persist_records(
                tenant_id=rule.tenant_id,
                activities=(activity,),
                notifications=(notification,),
                todos=(),
            )
            self.todo_service.mark_task_run(
                task=rule,
                next_run_at=next_run,
                last_run_at=now,
                status="pending",
            )
            return RecurringRuleRunResult(
                status="pending",
                next_run_at=next_run,
                last_run_at=now,
                activities=(activity,),
                notifications=(notification,),
            )

        orchestrator = self.orchestrator_cls(
            db=self.db,
            auth=auth,
            settings=self.settings,
        )
        mission_objective = str(automation.get("prompt") or rule.content).strip()
        mission_note_content = str(automation.get("note_content") or "").strip() or None

        if action_type == "connector_sync":
            connector_id = automation.get("connector_id")
            if connector_id:
                row = self.db.execute(
                    select(Connector, Integration)
                    .join(Integration, Connector.integration_id == Integration.id)
                    .where(Connector.id == connector_id)
                ).first()
                if row:
                    connector, integration = row
                    mission_objective = f"Sync connector {integration.slug}"
                    mission_note_content = "\n".join(
                        [
                            f"connector_id={connector.id}",
                            f"connector_name={connector.name}",
                            f"integration_slug={integration.slug}",
                        ]
                    )
                else:
                    notification = TriggerNotificationRecord(
                        recipient_user_id=rule.user_id,
                        message=(
                            "Connector sync skipped because connector "
                            f"{connector_id} was not found."
                        ),
                        idempotency_key=hashlib.sha256(
                            f"{rule.id}|connector_missing|{connector_id}|{run_marker}".encode()
                        ).hexdigest(),
                    )
                    self._persist_records(
                        tenant_id=rule.tenant_id,
                        activities=(),
                        notifications=(notification,),
                        todos=(),
                    )
                    self.todo_service.mark_task_run(
                        task=rule,
                        next_run_at=next_run,
                        last_run_at=now,
                        status="pending",
                    )
                    return RecurringRuleRunResult(
                        status="pending",
                        next_run_at=next_run,
                        last_run_at=now,
                        notifications=(notification,),
                    )

        mission = await orchestrator.execute_mission(
            objective=mission_objective,
            note_content=mission_note_content,
            execution_mode=self.mission_registry_cls(
                self.settings,
                db=self.db,
            ).get_execution_mode(
                tenant_id=str(rule.tenant_id),
                user_id=str(rule.user_id),
            ),
            await_approval=False,
        )

        status = str(mission.get("status") or "").lower()
        mission_id = str(mission.get("mission_id") or "") or None
        final_output = str(
            mission.get("final_output") or mission.get("summary") or ""
        ).strip()
        activities: list[TriggerActivityRecord] = []
        notifications: list[TriggerNotificationRecord] = []

        if status == "awaiting_approval":
            activities.append(
                TriggerActivityRecord(
                    activity_type="approval",
                    description=f"Approval needed for recurring task: {rule.content}",
                    source=str(automation.get("source") or "proactive"),
                    metadata_json={
                        "phase": "approval",
                        "task_id": str(rule.id),
                        "mission_id": mission_id,
                        "approval_queue": mission.get("approval_queue") or [],
                        "proactive_cycle_id": cycle_id,
                    },
                )
            )
            notifications.append(
                TriggerNotificationRecord(
                    recipient_user_id=rule.user_id,
                    message=f"Recurring task needs approval: {rule.content}",
                    idempotency_key=hashlib.sha256(
                        f"{rule.id}|awaiting_approval|{mission_id or run_marker}".encode()
                    ).hexdigest(),
                )
            )
        elif final_output:
            activities.append(
                TriggerActivityRecord(
                    activity_type="draft",
                    description=final_output[:300],
                    source=str(automation.get("source") or "proactive"),
                    metadata_json={
                        "phase": "result",
                        "task_id": str(rule.id),
                        "result": final_output,
                        "mission_id": mission_id,
                        "proactive_cycle_id": cycle_id,
                        "automation_json": automation,
                    },
                )
            )
            notifications.append(
                TriggerNotificationRecord(
                    recipient_user_id=rule.user_id,
                    message=f"Recurring task completed: {rule.content}",
                    idempotency_key=hashlib.sha256(
                        f"{rule.id}|completed|{mission_id or run_marker}".encode()
                    ).hexdigest(),
                )
            )

        self._persist_records(
            tenant_id=rule.tenant_id,
            activities=tuple(activities),
            notifications=tuple(notifications),
            todos=(),
        )
        self.todo_service.mark_task_run(
            task=rule,
            next_run_at=next_run,
            last_run_at=now,
            status=(
                "pending"
                if status == "awaiting_approval"
                else "completed" if final_output else "in_progress"
            ),
        )
        return RecurringRuleRunResult(
            status=(
                "pending"
                if status == "awaiting_approval"
                else "completed" if final_output else "in_progress"
            ),
            next_run_at=next_run,
            last_run_at=now,
            activities=tuple(activities),
            notifications=tuple(notifications),
            mission_id=mission_id,
            final_output=final_output or None,
        )

    def process_gmail_connector(
        self,
        *,
        conn,
        cycle_id: str,
    ) -> None:
        creds = (conn.config or {}).get("credentials")
        if not creds:
            return

        runtime = self.build_runtime(conn.config or {})
        if not runtime:
            return

        trigger = ProactiveTriggerRegistry.GMAIL_URGENT
        query = trigger.query
        processed_message_ids: set[str] = set()

        try:
            search_result = asyncio.run(
                runtime.call_tool("search_threads", {"query": query, "max_results": 5})
            )
            for candidate in self._extract_gmail_candidates(
                conn=conn,
                search_result=search_result,
                trigger=trigger,
            ):
                if candidate.message_id in processed_message_ids:
                    logger.info(
                        "Skipping repeated Gmail message %s for connector %s in the same scan.",
                        candidate.message_id,
                        candidate.connector_id,
                    )
                    continue
                if self.trigger_registry.already_processed(
                    trigger=trigger,
                    tenant_id=conn.tenant_id,
                    connector_id=candidate.connector_id,
                    external_id=candidate.message_id,
                ):
                    logger.info(
                        "Skipping already processed Gmail message %s for connector %s.",
                        candidate.message_id,
                        candidate.connector_id,
                    )
                    continue

                try:
                    msg_result = asyncio.run(
                        runtime.call_tool(
                            "get_thread", {"thread_id": candidate.message_id}
                        )
                    )
                    if not msg_result:
                        continue
                    subject = self._extract_subject(msg_result) or candidate.subject
                    self._record_gmail_match(
                        conn=conn,
                        candidate=GmailTriggerCandidate(
                            connector_id=candidate.connector_id,
                            connector_name=candidate.connector_name,
                            message_id=candidate.message_id,
                            subject=subject,
                            trigger_name=candidate.trigger_name,
                            trigger_version=candidate.trigger_version,
                        ),
                        cycle_id=cycle_id,
                        trigger=trigger,
                    )
                    processed_message_ids.add(candidate.message_id)
                    self.db.commit()
                    logger.info(
                        "Proactive intervention logged as activity for tenant %s: %s",
                        conn.tenant_id,
                        subject,
                    )
                except Exception as msg_exc:  # noqa: BLE001
                    self._record_gmail_message_failure(
                        conn=conn,
                        cycle_id=cycle_id,
                        candidate=candidate,
                        exc=msg_exc,
                    )
        except Exception as gmail_exc:  # noqa: BLE001
            self._record_gmail_scan_failure(
                conn=conn,
                cycle_id=cycle_id,
                exc=gmail_exc,
            )

    def failure_notification_suppressed(
        self,
        *,
        tenant_id,
        failure_idempotency_key: str,
    ) -> bool:
        cutoff = datetime.now(UTC) - timedelta(days=14)
        if hasattr(self.db, "query"):
            rows = (
                self.db.query(AgentActivity.metadata_json)
                .filter(
                    AgentActivity.tenant_id == tenant_id,
                    AgentActivity.source == "gmail",
                    AgentActivity.activity_type == "error",
                    AgentActivity.created_at >= cutoff,
                )
                .order_by(AgentActivity.created_at.desc())
                .limit(100)
                .all()
            )
        else:
            rows = []
        now = datetime.now(UTC)
        for metadata in rows:
            if not isinstance(metadata, dict):
                try:
                    metadata = metadata[0]
                except Exception:  # noqa: BLE001
                    pass
            if not isinstance(metadata, dict):
                continue
            if (
                str(metadata.get("failure_idempotency_key") or "")
                != failure_idempotency_key
            ):
                continue
            retry_after_at = str(metadata.get("retry_after_at") or "").strip()
            if not retry_after_at:
                return True
            try:
                parsed = datetime.fromisoformat(retry_after_at.replace("Z", "+00:00"))
            except ValueError:
                return True
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            if parsed > now:
                return True
        return False

    def retry_after_at(self, *, delay_minutes: int = 10) -> str:
        return (
            (datetime.now(UTC) + timedelta(minutes=max(1, delay_minutes)))
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _persist_records(
        self,
        *,
        tenant_id,
        activities: tuple[TriggerActivityRecord, ...],
        notifications: tuple[TriggerNotificationRecord, ...],
        todos: tuple[TriggerTodoRecord, ...],
    ) -> None:
        for activity in activities:
            self.db.add(
                AgentActivity(
                    tenant_id=tenant_id,
                    activity_type=activity.activity_type,
                    description=activity.description,
                    source=activity.source,
                    metadata_json=activity.metadata_json,
                )
            )
        for todo in todos:
            self.todo_service.upsert_task(
                tenant_id=str(tenant_id),
                user_id=str(todo.metadata_json.get("user_id") or ""),
                content=todo.content,
                active_form=todo.active_form,
                status=todo.status,
                priority=todo.priority,
                metadata_json=todo.metadata_json,
            )
        for notification in notifications:
            self.notify_proactive(
                db=self.db,
                recipient_user_id=notification.recipient_user_id,
                message=notification.message,
                idempotency_key=notification.idempotency_key,
            )

    def _extract_gmail_candidates(
        self,
        *,
        conn,
        search_result,
        trigger: ProactiveTrigger,
    ) -> list[GmailTriggerCandidate]:
        threads = []
        if hasattr(search_result, "threads"):
            threads = search_result.threads
        elif isinstance(search_result, dict) and "threads" in search_result:
            threads = search_result["threads"]
        elif hasattr(search_result, "structuredContent"):
            struct = getattr(search_result, "structuredContent", None)
            if isinstance(struct, dict):
                threads = struct.get("threads") or struct.get("items") or []

        candidates: list[GmailTriggerCandidate] = []
        connector_id = str(conn.id)
        connector_name = str(conn.name)
        for thread in threads:
            message_id = (
                thread.get("id")
                if isinstance(thread, dict)
                else getattr(thread, "id", None)
            )
            if not message_id:
                continue
            candidates.append(
                GmailTriggerCandidate(
                    connector_id=connector_id,
                    connector_name=connector_name,
                    message_id=str(message_id),
                    subject="No Subject",
                    trigger_name=trigger.name,
                    trigger_version=trigger.version,
                )
            )
        return candidates

    def _extract_subject(self, msg_result) -> str:
        messages_list = []
        if hasattr(msg_result, "messages"):
            messages_list = msg_result.messages
        elif isinstance(msg_result, dict) and "messages" in msg_result:
            messages_list = msg_result["messages"]
        elif hasattr(msg_result, "structuredContent"):
            struct = getattr(msg_result, "structuredContent", None)
            if isinstance(struct, dict):
                messages_list = struct.get("messages") or []

        if not messages_list:
            return "No Subject"
        first_msg = messages_list[0]
        headers = (
            first_msg.get("payload", {}).get("headers", [])
            if isinstance(first_msg, dict)
            else getattr(getattr(first_msg, "payload", object()), "headers", [])
        )
        for header in headers:
            header_name = (
                header.get("name")
                if isinstance(header, dict)
                else getattr(header, "name", "")
            )
            if header_name == "Subject":
                return (
                    header.get("value")
                    if isinstance(header, dict)
                    else getattr(header, "value", "No Subject")
                )
        return "No Subject"

    def _record_gmail_match(
        self,
        *,
        conn,
        candidate: GmailTriggerCandidate,
        cycle_id: str,
        trigger: ProactiveTrigger,
    ) -> None:
        draft_body = (
            f"Subject: {candidate.subject}\n\nI found an urgent email in Gmail. "
            "Draft a concise reply and confirm before sending."
        )
        trigger_metadata = self.trigger_registry.metadata(
            trigger=trigger,
            tenant_id=conn.tenant_id,
            connector_id=candidate.connector_id,
            external_id=candidate.message_id,
            extra={
                "message_id": candidate.message_id,
                "connector_name": candidate.connector_name,
            },
        )
        self.db.add(
            AgentActivity(
                tenant_id=conn.tenant_id,
                activity_type="match",
                description=f"Matched urgent email: '{candidate.subject}'.",
                source="gmail",
                metadata_json={
                    **trigger_metadata,
                    "phase": "match",
                    "draft_title": candidate.subject,
                    "draft_body": draft_body,
                    "draft_html": f"<p>{draft_body.replace(chr(10), '<br />')}</p>",
                    "proactive_cycle_id": cycle_id,
                },
            )
        )
        self.db.add(
            AgentActivity(
                tenant_id=conn.tenant_id,
                activity_type="draft",
                description=f"Prepared draft for urgent email: '{candidate.subject}'.",
                source="gmail",
                metadata_json={
                    **trigger_metadata,
                    "phase": "draft",
                    "draft_title": f"Reply to: {candidate.subject}",
                    "draft_body": draft_body,
                    "draft_html": f"<p>{draft_body.replace(chr(10), '<br />')}</p>",
                    "proactive_cycle_id": cycle_id,
                },
            )
        )
        self.todo_service.upsert_task(
            tenant_id=str(conn.tenant_id),
            user_id=str(conn.user_id),
            content=f"Reply to urgent Gmail: {candidate.subject}",
            active_form=f"Reply to urgent Gmail: {candidate.subject}",
            status="pending",
            priority=70,
            metadata_json={
                **trigger_metadata,
                "source": "gmail",
                "phase": "draft",
                "draft_title": f"Reply to: {candidate.subject}",
                "proactive_cycle_id": cycle_id,
            },
        )
        self.notify_proactive(
            db=self.db,
            recipient_user_id=conn.user_id,
            message=f"Urgent Gmail found for {conn.name}: {candidate.subject}",
            idempotency_key=trigger_metadata["idempotency_key"],
        )

    def _record_gmail_message_failure(
        self,
        *,
        conn,
        cycle_id: str,
        candidate: GmailTriggerCandidate,
        exc: Exception,
    ) -> None:
        retry_after_at = self.retry_after_at(delay_minutes=15)
        failure_idempotency_key = hashlib.sha256(
            (
                f"{conn.tenant_id}|{conn.id}|gmail_message_failed|"
                f"{candidate.message_id}|{exc.__class__.__name__}"
            ).encode()
        ).hexdigest()
        logger.error(
            "Gmail proactive message handling failed for connector %s message %s: %s",
            conn.id,
            candidate.message_id,
            exc,
        )
        self.db.rollback()
        suppress_alert = self.failure_notification_suppressed(
            tenant_id=conn.tenant_id,
            failure_idempotency_key=failure_idempotency_key,
        )
        self.db.add(
            AgentActivity(
                tenant_id=conn.tenant_id,
                activity_type="error",
                description=f"Gmail proactive message handling failed for {conn.name}.",
                source="gmail",
                metadata_json={
                    "phase": "gmail_message",
                    "connector_id": str(conn.id),
                    "connector_name": conn.name,
                    "integration_slug": (
                        conn.integration.slug if conn.integration else None
                    ),
                    "message_id": candidate.message_id,
                    "error_code": "gmail_message_failed",
                    "failure_idempotency_key": failure_idempotency_key,
                    "retryable": True,
                    "retry_after_at": retry_after_at,
                    "message": str(exc),
                    "proactive_cycle_id": cycle_id,
                },
            )
        )
        if not suppress_alert:
            self.todo_service.upsert_task(
                tenant_id=str(conn.tenant_id),
                user_id=str(conn.user_id),
                content=f"Investigate Gmail proactive message failure for {conn.name}",
                active_form=f"Investigate Gmail proactive message failure for {conn.name}",
                status="pending",
                priority=85,
                metadata_json={
                    "source": "gmail",
                    "phase": "gmail_message",
                    "connector_id": str(conn.id),
                    "connector_name": conn.name,
                    "message_id": candidate.message_id,
                    "error_code": "gmail_message_failed",
                    "failure_idempotency_key": failure_idempotency_key,
                    "retryable": True,
                    "retry_after_at": retry_after_at,
                    "message": str(exc),
                    "proactive_cycle_id": cycle_id,
                },
            )
            self.notify_proactive(
                db=self.db,
                recipient_user_id=conn.user_id,
                message=f"Gmail message handling failed for {conn.name}.",
                idempotency_key=failure_idempotency_key,
            )
        self.db.commit()

    def _record_gmail_scan_failure(
        self,
        *,
        conn,
        cycle_id: str,
        exc: Exception,
    ) -> None:
        retry_after_at = self.retry_after_at(delay_minutes=15)
        failure_idempotency_key = hashlib.sha256(
            f"{conn.tenant_id}|{conn.id}|gmail_scan_failed|{exc.__class__.__name__}".encode()
        ).hexdigest()
        logger.error("Gmail proactive scan failed for connector %s: %s", conn.id, exc)
        self.db.rollback()
        suppress_alert = self.failure_notification_suppressed(
            tenant_id=conn.tenant_id,
            failure_idempotency_key=failure_idempotency_key,
        )
        self.db.add(
            AgentActivity(
                tenant_id=conn.tenant_id,
                activity_type="error",
                description=f"Gmail proactive scan failed for {conn.name}.",
                source="gmail",
                metadata_json={
                    "phase": "gmail_scan",
                    "connector_id": str(conn.id),
                    "connector_name": conn.name,
                    "integration_slug": (
                        conn.integration.slug if conn.integration else None
                    ),
                    "error_code": "gmail_scan_failed",
                    "failure_idempotency_key": failure_idempotency_key,
                    "retryable": True,
                    "retry_after_at": retry_after_at,
                    "message": str(exc),
                    "proactive_cycle_id": cycle_id,
                },
            )
        )
        if not suppress_alert:
            self.todo_service.upsert_task(
                tenant_id=str(conn.tenant_id),
                user_id=str(conn.user_id),
                content=f"Investigate Gmail proactive scan failure for {conn.name}",
                active_form=f"Investigate Gmail proactive scan failure for {conn.name}",
                status="pending",
                priority=85,
                metadata_json={
                    "source": "gmail",
                    "phase": "gmail_scan",
                    "connector_id": str(conn.id),
                    "connector_name": conn.name,
                    "error_code": "gmail_scan_failed",
                    "failure_idempotency_key": failure_idempotency_key,
                    "retryable": True,
                    "retry_after_at": retry_after_at,
                    "message": str(exc),
                    "proactive_cycle_id": cycle_id,
                },
            )
            self.notify_proactive(
                db=self.db,
                recipient_user_id=conn.user_id,
                message=f"Gmail proactive scan failed for {conn.name}.",
                idempotency_key=failure_idempotency_key,
            )
        self.db.commit()


def build_trigger_runner(
    *,
    db,
    settings,
    todo_service,
    mission_registry_cls,
    orchestrator_cls,
    build_runtime: Callable[[dict[str, Any]], Any],
    notify_proactive: Callable[..., None],
) -> TriggerRunner:
    return TriggerRunner(
        db=db,
        settings=settings,
        todo_service=todo_service,
        mission_registry_cls=mission_registry_cls,
        orchestrator_cls=orchestrator_cls,
        build_runtime=build_runtime,
        notify_proactive=notify_proactive,
    )
