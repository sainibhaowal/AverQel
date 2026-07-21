from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.deepspace.models.agent_activity import AgentActivity
from app.deepspace.models.agent_todo import AgentTodo
from app.deepspace.proactive.proactive_triggers import ProactiveTriggerRegistry
from app.deepspace.workers import tasks_proactive
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.integration import Integration
from app.integrations.workers import tasks_connectors


@dataclass
class _FakeTask:
    id: str
    tenant_id: str
    user_id: str
    content: str
    active_form: str
    automation_json: dict[str, object]
    status: str = "pending"


class _FakeTodoService:
    def __init__(self, db):  # noqa: ARG002
        self.marked: list[dict[str, object]] = []
        self.upserted: list[dict[str, object]] = []
        self.due_rules: list[object] = []

    def mark_task_run(self, *, task, next_run_at, last_run_at, status):  # noqa: ARG002
        if hasattr(task, "next_run_at"):
            task.next_run_at = next_run_at
        if hasattr(task, "last_run_at"):
            task.last_run_at = last_run_at
        if hasattr(task, "status"):
            task.status = status
        self.marked.append({"task": task.id, "status": status})

    def list_due_recurring_tasks(self, *, tenant_id, user_id):  # noqa: ARG002
        return list(self.due_rules)

    def upsert_task(
        self,
        *,
        tenant_id,
        user_id,
        content,
        active_form,
        status,
        priority,
        metadata_json,
    ):  # noqa: ARG002
        self.upserted.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "content": content,
                "active_form": active_form,
                "status": status,
                "priority": priority,
                "metadata_json": metadata_json,
            }
        )


class _FakeMissionRegistry:
    def __init__(self, settings, db=None):  # noqa: ARG002
        _ = (settings, db)

    def get_execution_mode(
        self, *, tenant_id, user_id, conversation_id=None
    ):  # noqa: ARG002
        return "auto_review"


class _FakeMissionOrchestrator:
    last_call: dict[str, object] | None = None
    last_support_call: dict[str, object] | None = None
    support_call_count: int = 0
    support_should_fail: bool = False

    def __init__(self, *args, **kwargs):  # noqa: ARG002
        self.registry = SimpleNamespace(
            get_execution_mode=lambda **kwargs: "auto_review",
        )

    async def execute_mission(self, **kwargs):  # noqa: ARG002
        _FakeMissionOrchestrator.last_call = kwargs
        return {
            "mission_id": str(uuid4()),
            "status": "completed",
            "summary": "done",
            "final_output": "done",
        }

    async def execute_support_mission(self, **kwargs):  # noqa: ARG002
        _FakeMissionOrchestrator.last_support_call = kwargs
        _FakeMissionOrchestrator.support_call_count += 1
        if _FakeMissionOrchestrator.support_should_fail:
            raise RuntimeError("support mission unavailable")
        return {
            "mission_id": str(uuid4()),
            "status": "completed",
            "healthy": True,
            "vitals": {
                "internet": "connected",
                "llm": "connected",
                "web_search": "available",
                "sources": 1,
            },
            "connector_health": {},
            "daemon_heartbeat": {
                "phase": "running",
                "timestamp": "2026-05-22T08:35:00Z",
            },
            "summary": "support ok",
            "final_output": "support ok",
        }

    def sync_connector(
        self, connector_id, tenant_id, progress_callback=None, attempt=1
    ):  # noqa: ARG002
        _FakeMissionOrchestrator.last_call = {
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "attempt": attempt,
        }
        return {"status": "success", "document_id": "doc-1"}


class _FakeProactiveDb:
    def __init__(self, connectors):
        self.connectors = connectors
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0
        self._execute_count = 0

    def execute(self, stmt):  # noqa: ARG002
        self._execute_count += 1
        if self._execute_count == 1:
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: self.connectors)
            )
        return SimpleNamespace(all=lambda: [])

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeConnectorRow:
    def __init__(self):
        self.id = uuid4()
        self.tenant_id = uuid4()
        self.user_id = uuid4()
        self.name = "Gmail"
        self.integration = SimpleNamespace(slug="gmail")
        self.config = {}


class _FakeSession:
    def __init__(self, row):
        self.row = row
        self.connector = row[0]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ARG002
        return False

    def execute(self, stmt, params=None):  # noqa: ARG002
        class _Result:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

            def scalar(self):
                return True

        return _Result(self.row)

    def get(self, model, identity):  # noqa: ARG002
        return self.connector

    def expire_all(self):
        return None

    def close(self):
        return None


@pytest.mark.asyncio
async def test_recurring_rule_routes_through_master_orchestrator(
    monkeypatch, db_session
):
    fake_task = _FakeTask(
        id="task-1",
        tenant_id=str(uuid4()),
        user_id=str(uuid4()),
        content="Daily briefing",
        active_form="Daily briefing",
        automation_json={
            "action_type": "agent_prompt",
            "prompt": "Prepare the daily brief.",
            "schedule_type": "daily",
        },
    )

    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)
    _FakeMissionOrchestrator.last_call = None
    todo_service = _FakeTodoService(db_session)

    await tasks_proactive._run_recurring_rule(
        db=db_session, todo_service=todo_service, rule=fake_task
    )

    assert _FakeMissionOrchestrator.last_call is not None
    assert _FakeMissionOrchestrator.last_call["objective"] == "Prepare the daily brief."
    assert todo_service.marked[-1]["status"] == "completed"


def test_proactive_cycle_routes_support_checks_through_master_orchestrator(
    monkeypatch,
) -> None:
    connector = SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        name="Support Connector",
        integration=SimpleNamespace(slug="slack"),
    )
    db = _FakeProactiveDb([connector])
    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)
    _FakeMissionOrchestrator.last_support_call = None

    tasks_proactive._run_proactive_cycle(db)

    assert _FakeMissionOrchestrator.last_support_call is not None
    assert (
        _FakeMissionOrchestrator.last_support_call.get("execution_mode")
        == "auto_review"
    )


def test_proactive_cycle_reuses_support_report_for_shared_tenant_user(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connectors = [
        SimpleNamespace(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name="Support Connector A",
            integration=SimpleNamespace(slug="slack"),
        ),
        SimpleNamespace(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name="Support Connector B",
            integration=SimpleNamespace(slug="gmail"),
        ),
    ]
    db = _FakeProactiveDb(connectors)
    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)
    _FakeMissionOrchestrator.last_support_call = None
    _FakeMissionOrchestrator.support_call_count = 0

    tasks_proactive._run_proactive_cycle(db)

    assert _FakeMissionOrchestrator.support_call_count == 1


def test_proactive_cycle_caches_support_mission_failures_for_shared_tenant_user(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connectors = [
        SimpleNamespace(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name="Support Connector A",
            integration=SimpleNamespace(slug="slack"),
        ),
        SimpleNamespace(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name="Support Connector B",
            integration=SimpleNamespace(slug="gmail"),
        ),
    ]
    db = _FakeProactiveDb(connectors)
    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)
    todo_service = _FakeTodoService(db)
    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)
    _FakeMissionOrchestrator.last_support_call = None
    _FakeMissionOrchestrator.support_call_count = 0
    _FakeMissionOrchestrator.support_should_fail = True

    try:
        tasks_proactive._run_proactive_cycle(db)
    finally:
        _FakeMissionOrchestrator.support_should_fail = False

    assert _FakeMissionOrchestrator.support_call_count == 1
    assert todo_service.upserted
    metadata = todo_service.upserted[0]["metadata_json"]
    assert metadata["support_report_error_code"] == "support_mission_failed"
    assert metadata["support_report_status"] == "degraded"
    assert "support mission unavailable" in metadata["support_report_summary"]


def test_proactive_cycle_records_gmail_scan_failures_as_structured_activity(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connectors = [
        SimpleNamespace(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name="Gmail Connector",
            integration=SimpleNamespace(slug="gmail"),
            config={"credentials": {"access_token": "token"}},
        )
    ]
    db = _FakeProactiveDb(connectors)
    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)

    async def _failing_call(name, _args):
        if name == "search_threads":
            raise RuntimeError("gmail down")
        return None

    monkeypatch.setattr(
        tasks_proactive,
        "build_mcp_runtime",
        lambda _config: SimpleNamespace(call_tool=_failing_call),
    )
    todo_service = _FakeTodoService(db)

    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)
    _FakeMissionOrchestrator.support_should_fail = False
    _FakeMissionOrchestrator.support_call_count = 0

    tasks_proactive._run_proactive_cycle(db)

    error_activities = [
        item
        for item in db.added
        if isinstance(item, AgentActivity)
        and item.activity_type == "error"
        and (item.metadata_json or {}).get("error_code") == "gmail_scan_failed"
    ]
    assert error_activities
    assert error_activities[0].metadata_json["retryable"] is True
    assert error_activities[0].metadata_json["retry_after_at"]
    assert error_activities[0].metadata_json["proactive_cycle_id"]
    assert todo_service.upserted
    assert (
        todo_service.upserted[0]["metadata_json"]["error_code"] == "gmail_scan_failed"
    )
    assert todo_service.upserted[0]["metadata_json"]["retryable"] is True
    assert todo_service.upserted[0]["metadata_json"]["retry_after_at"]


def test_proactive_cycle_marks_recurring_failures_retryable_and_continues(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Retry Tenant",
        "proactive-retry@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    due_rule = AgentTodo(
        id=str(uuid4()),
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        content="Prepare the daily brief",
        active_form="Prepare the daily brief",
        status="pending",
        priority=50,
        metadata_json={},
        automation_json={
            "action_type": "agent_prompt",
            "prompt": "Prepare the daily brief.",
            "schedule_type": "daily",
        },
        is_recurring=1,
        enabled=1,
        next_run_at=datetime.now(UTC) - timedelta(minutes=5),
        last_run_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(due_rule)
    db_session.commit()

    class _FailingMissionOrchestrator:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            self.registry = SimpleNamespace(
                get_execution_mode=lambda **kwargs: "auto_review",
            )

        async def execute_mission(self, **kwargs):  # noqa: ARG002
            raise RuntimeError("mission failed")

    todo_service = _FakeTodoService(db_session)
    todo_service.due_rules = [due_rule]
    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(
        tasks_proactive, "MasterOrchestrator", _FailingMissionOrchestrator
    )
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)
    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)

    tasks_proactive._run_proactive_cycle(db_session)

    db_session.refresh(due_rule)
    assert due_rule.status == "pending"
    assert due_rule.next_run_at is not None
    next_run_at = due_rule.next_run_at
    if next_run_at.tzinfo is None:
        next_run_at = next_run_at.replace(tzinfo=UTC)
    assert next_run_at > datetime.now(UTC)

    error_activity = (
        db_session.query(AgentActivity)
        .filter(AgentActivity.tenant_id == seeded.tenant_id)
        .filter(AgentActivity.activity_type == "error")
        .order_by(AgentActivity.created_at.desc())
        .first()
    )
    assert error_activity is not None
    assert error_activity.metadata_json["retryable"] is True
    assert error_activity.metadata_json["retry_after_at"]
    assert error_activity.metadata_json["retry_reference"]
    assert error_activity.metadata_json["proactive_cycle_id"]
    assert todo_service.marked[-1]["status"] == "pending"


def test_proactive_cycle_persists_successful_gmail_messages_when_a_later_message_fails(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Gmail Tenant",
        "proactive-gmail@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    gmail_integration_name = f"Gmail Integration {uuid4().hex[:8]}"
    integration = db_session.query(Integration).filter_by(slug="gmail").one_or_none()
    if integration is None:
        integration = Integration(
            name=gmail_integration_name,
            slug="gmail",
            description="Gmail integration",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        integration_id=integration.id,
        name="Gmail Connector",
        status=ConnectorStatus.ACTIVE,
        config={"credentials": {"access_token": "token"}},
    )
    db_session.add(connector)
    db_session.commit()

    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)

    async def _sequence_call(name, args):
        if name == "search_threads":
            # Correct MCP return for search_threads
            return SimpleNamespace(
                threads=[{"id": "gmail-message-1"}, {"id": "gmail-message-2"}]
            )
        if name == "get_thread":
            msg_id = args.get("thread_id")
            if msg_id == "gmail-message-2":
                raise RuntimeError("message payload unavailable")
            return SimpleNamespace(
                messages=[
                    {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Urgent first"},
                            ]
                        }
                    }
                ]
            )
        return None

    monkeypatch.setattr(
        tasks_proactive,
        "build_mcp_runtime",
        lambda _config: SimpleNamespace(call_tool=_sequence_call),
    )
    todo_service = _FakeTodoService(db_session)

    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)
    _FakeMissionOrchestrator.support_should_fail = False
    _FakeMissionOrchestrator.support_call_count = 0

    tasks_proactive._run_proactive_cycle(db_session)

    match_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type in {"match", "draft"}
    ]
    error_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type == "error"
        and (item.metadata_json or {}).get("error_code") == "gmail_message_failed"
    ]

    assert any(
        item.activity_type == "match" and "Urgent first" in item.description
        for item in match_activities
    )
    assert any(
        item.activity_type == "draft" and "Urgent first" in item.description
        for item in match_activities
    )
    assert error_activities
    assert todo_service.upserted
    assert any(
        entry["metadata_json"].get("error_code") == "gmail_message_failed"
        for entry in todo_service.upserted
    )
    assert any(
        entry["metadata_json"].get("retryable") is True
        for entry in todo_service.upserted
        if entry["metadata_json"].get("error_code") == "gmail_message_failed"
    )


def test_proactive_cycle_dedupes_repeated_gmail_message_failure_notifications(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Gmail Message Failure Tenant",
        "proactive-gmail-message-failure@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    gmail_integration_name = f"Gmail Integration {uuid4().hex[:8]}"
    integration = db_session.query(Integration).filter_by(slug="gmail").one_or_none()
    if integration is None:
        integration = Integration(
            name=gmail_integration_name,
            slug="gmail",
            description="Gmail integration",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        integration_id=integration.id,
        name="Gmail Connector",
        status=ConnectorStatus.ACTIVE,
        config={"credentials": {"access_token": "token"}},
    )
    db_session.add(connector)
    db_session.commit()

    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)

    async def _failing_message_call(name, args):
        if name == "search_threads":
            return SimpleNamespace(threads=[{"id": "gmail-message-1"}])
        if name == "get_thread":
            assert args.get("thread_id") == "gmail-message-1"
            raise RuntimeError("message payload unavailable")
        return None

    monkeypatch.setattr(
        tasks_proactive,
        "build_mcp_runtime",
        lambda _config: SimpleNamespace(call_tool=_failing_message_call),
    )
    todo_service = _FakeTodoService(db_session)

    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)

    tasks_proactive._run_proactive_cycle(db_session)
    tasks_proactive._run_proactive_cycle(db_session)

    notifications = (
        db_session.query(tasks_proactive.CollectionNotification)
        .filter_by(recipient_user_id=seeded.user_id)
        .all()
    )
    error_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type == "error"
        and (item.metadata_json or {}).get("error_code") == "gmail_message_failed"
    ]

    assert len(notifications) == 1
    assert len(error_activities) == 2
    assert all(item.metadata_json["retryable"] is True for item in error_activities)
    assert all(item.metadata_json["retry_after_at"] for item in error_activities)
    assert len(todo_service.upserted) == 1


def test_proactive_cycle_recovers_after_gmail_scan_failure_and_processes_message(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Gmail Recovery Tenant",
        "proactive-gmail-recovery@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    gmail_integration_name = f"Gmail Integration {uuid4().hex[:8]}"
    integration = db_session.query(Integration).filter_by(slug="gmail").one_or_none()
    if integration is None:
        integration = Integration(
            name=gmail_integration_name,
            slug="gmail",
            description="Gmail integration",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        integration_id=integration.id,
        name="Gmail Connector",
        status=ConnectorStatus.ACTIVE,
        config={"credentials": {"access_token": "token"}},
    )
    db_session.add(connector)
    db_session.commit()

    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)

    class _RecoverState:
        attempts = 0

    async def _recovering_call(name, args):
        if name == "search_threads":
            _RecoverState.attempts += 1
            if _RecoverState.attempts == 1:
                raise RuntimeError("gmail temporarily down")
            return SimpleNamespace(threads=[{"id": "gmail-message-1"}])
        if name == "get_thread":
            assert args.get("thread_id") == "gmail-message-1"
            return SimpleNamespace(
                messages=[
                    {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Recovered urgent thread"},
                            ]
                        }
                    }
                ]
            )
        return None

    monkeypatch.setattr(
        tasks_proactive,
        "build_mcp_runtime",
        lambda _config: SimpleNamespace(call_tool=_recovering_call),
    )

    todo_service = _FakeTodoService(db_session)
    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)
    monkeypatch.setattr(tasks_proactive, "_notify_proactive", lambda **kwargs: None)

    tasks_proactive._run_proactive_cycle(db_session)
    tasks_proactive._run_proactive_cycle(db_session)

    error_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type == "error"
        and (item.metadata_json or {}).get("error_code") == "gmail_scan_failed"
    ]
    match_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type in {"match", "draft"}
    ]

    assert len(error_activities) == 1
    assert any(
        "Recovered urgent thread" in item.description for item in match_activities
    )
    assert len(todo_service.upserted) >= 2


def test_proactive_cycle_dedupes_repeated_gmail_scan_failure_notifications(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Gmail Failure Tenant",
        "proactive-gmail-failure@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    gmail_integration_name = f"Gmail Integration {uuid4().hex[:8]}"
    integration = db_session.query(Integration).filter_by(slug="gmail").one_or_none()
    if integration is None:
        integration = Integration(
            name=gmail_integration_name,
            slug="gmail",
            description="Gmail integration",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        integration_id=integration.id,
        name="Gmail Connector",
        status=ConnectorStatus.ACTIVE,
        config={"credentials": {"access_token": "token"}},
    )
    db_session.add(connector)
    db_session.commit()

    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)

    async def _always_fail_call(name, args):
        if name == "search_threads":
            raise RuntimeError("gmail scan unavailable")
        return None

    monkeypatch.setattr(
        tasks_proactive,
        "build_mcp_runtime",
        lambda _config: SimpleNamespace(call_tool=_always_fail_call),
    )

    todo_service = _FakeTodoService(db_session)
    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)
    tasks_proactive._run_proactive_cycle(db_session)
    tasks_proactive._run_proactive_cycle(db_session)

    error_notifications = (
        db_session.query(tasks_proactive.CollectionNotification)
        .filter_by(recipient_user_id=seeded.user_id)
        .all()
    )
    error_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type == "error"
        and (item.metadata_json or {}).get("error_code") == "gmail_scan_failed"
    ]

    assert len(error_notifications) == 1
    assert len(error_activities) == 2


def test_proactive_cycle_dedupes_repeated_gmail_notifications_and_activity(
    db_session,
    seed_user,
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Gmail Dedupe Tenant",
        "proactive-gmail-dedupe@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    gmail_integration_name = f"Gmail Integration {uuid4().hex[:8]}"
    integration = db_session.query(Integration).filter_by(slug="gmail").one_or_none()
    if integration is None:
        integration = Integration(
            name=gmail_integration_name,
            slug="gmail",
            description="Gmail integration",
            ui_metadata={},
        )
        db_session.add(integration)
        db_session.flush()
    connector = Connector(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        integration_id=integration.id,
        name="Gmail Connector",
        status=ConnectorStatus.ACTIVE,
        config={"credentials": {"access_token": "token"}},
    )
    db_session.add(connector)
    db_session.commit()

    monkeypatch.setattr(tasks_proactive, "MissionRegistry", _FakeMissionRegistry)
    monkeypatch.setattr(tasks_proactive, "MasterOrchestrator", _FakeMissionOrchestrator)

    async def _dedupe_call(name, args):
        if name == "search_threads":
            return SimpleNamespace(
                threads=[{"id": "gmail-message-1"}, {"id": "gmail-message-1"}]
            )
        if name == "get_thread":
            assert args.get("thread_id") == "gmail-message-1"
            return SimpleNamespace(
                messages=[
                    {
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Urgent first"},
                            ]
                        }
                    }
                ]
            )
        return None

    monkeypatch.setattr(
        tasks_proactive,
        "build_mcp_runtime",
        lambda _config: SimpleNamespace(call_tool=_dedupe_call),
    )
    todo_service = _FakeTodoService(db_session)

    monkeypatch.setattr(tasks_proactive, "TodoService", lambda db: todo_service)
    _FakeMissionOrchestrator.support_should_fail = False
    _FakeMissionOrchestrator.support_call_count = 0

    tasks_proactive._run_proactive_cycle(db_session)
    tasks_proactive._run_proactive_cycle(db_session)

    gmail_activities = [
        item
        for item in db_session.query(AgentActivity).all()
        if item.tenant_id == seeded.tenant_id
        and item.source == "gmail"
        and item.activity_type in {"match", "draft"}
    ]
    notifications = (
        db_session.query(tasks_proactive.CollectionNotification)
        .filter_by(recipient_user_id=seeded.user_id)
        .all()
    )

    assert (
        len([item for item in gmail_activities if item.activity_type == "match"]) == 1
    )
    assert (
        len([item for item in gmail_activities if item.activity_type == "draft"]) == 1
    )
    assert len(notifications) == 1
    assert len(todo_service.upserted) == 1
    assert any(
        entry["metadata_json"].get("trigger_version") == "gmail-urgent-v1"
        for entry in todo_service.upserted
    )


def test_proactive_gmail_dedupe_uses_persisted_activity(db_session) -> None:
    tenant_id = uuid4()
    connector_id = str(uuid4())
    message_id = "gmail-message-1"
    db_session.add(
        AgentActivity(
            tenant_id=tenant_id,
            activity_type="draft",
            description="Prepared draft for urgent email.",
            source="gmail",
            metadata_json={
                "connector_id": connector_id,
                "message_id": message_id,
                "trigger_version": "gmail-urgent-v1",
            },
        )
    )
    db_session.commit()

    assert tasks_proactive._already_processed_gmail_message(
        db=db_session,
        tenant_id=tenant_id,
        connector_id=connector_id,
        message_id=message_id,
    )
    assert not tasks_proactive._already_processed_gmail_message(
        db=db_session,
        tenant_id=tenant_id,
        connector_id=connector_id,
        message_id="different-message",
    )


def test_proactive_trigger_registry_adds_idempotency_metadata(db_session) -> None:
    tenant_id = uuid4()
    connector_id = str(uuid4())
    message_id = "gmail-message-42"
    registry = ProactiveTriggerRegistry(db_session)
    metadata = registry.metadata(
        trigger=ProactiveTriggerRegistry.GMAIL_URGENT,
        tenant_id=tenant_id,
        connector_id=connector_id,
        external_id=message_id,
        extra={"message_id": message_id},
    )

    assert metadata["trigger_version"] == "gmail-urgent-v1"
    assert metadata["idempotency_key"]
    assert metadata["trigger_cooldown_seconds"] > 0
    assert metadata["trigger_cooldown_until"]

    db_session.add(
        AgentActivity(
            tenant_id=tenant_id,
            activity_type="match",
            description="Matched urgent email.",
            source="gmail",
            metadata_json=metadata,
        )
    )
    db_session.commit()

    assert registry.already_processed(
        trigger=ProactiveTriggerRegistry.GMAIL_URGENT,
        tenant_id=tenant_id,
        connector_id=connector_id,
        external_id=message_id,
    )


def test_connector_sync_routes_through_master_orchestrator(monkeypatch):
    fake_row = (
        _FakeConnectorRow(),
        SimpleNamespace(slug="gmail"),
    )
    fake_session = _FakeSession(fake_row)

    monkeypatch.setattr(
        tasks_connectors, "get_session_factory", lambda: (lambda: fake_session)
    )
    monkeypatch.setattr(
        tasks_connectors, "ConnectorOrchestrator", _FakeMissionOrchestrator
    )
    monkeypatch.setattr(tasks_connectors, "get_settings", lambda: SimpleNamespace())

    tasks_connectors.run_connector_sync_task.__wrapped__(str(fake_row[0].id))

    assert _FakeMissionOrchestrator.last_call is not None
    assert _FakeMissionOrchestrator.last_call["connector_id"] == fake_row[0].id
    assert _FakeMissionOrchestrator.last_call["tenant_id"] == fake_row[0].tenant_id
