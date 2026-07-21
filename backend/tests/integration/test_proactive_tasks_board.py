from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.deepspace.models.agent_activity import AgentActivity
from app.deepspace.memory.memory_service import TodoService
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...]) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_proactive_tasks_endpoint_returns_persisted_records(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Proactive Ledger Tenant",
        "ledger@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    todo_service = TodoService(db_session)
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Review Gmail sync: Urgent inbox",
        active_form="Review Gmail sync: Urgent inbox",
        status="pending",
        priority=80,
        metadata_json={
            "source": "gmail",
            "phase": "draft",
        },
    )
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Investigate GitHub sync failure",
        active_form="Investigate GitHub sync failure",
        status="in_progress",
        priority=90,
        metadata_json={
            "source": "github",
            "phase": "error",
        },
    )
    create_response = client.post(
        "/api/v1/deepspace/chats/tasks",
        headers=headers,
        json={
            "content": "Fetch daily news digest",
            "activeForm": "Fetch daily news digest",
            "status": "pending",
            "priority": 50,
            "is_recurring": True,
            "enabled": True,
            "next_run_at": datetime(2026, 5, 7, 9, 0, tzinfo=UTC).isoformat(),
            "automation_json": {
                "action_type": "agent_prompt",
                "schedule_type": "daily",
                "prompt": "Fetch the latest news and summarize it.",
                "web_search_enabled": True,
            },
            "metadata_json": {
                "source": "web-crawler",
                "phase": "schedule",
            },
        },
    )
    assert create_response.status_code == 200
    recurring_id = create_response.json()["id"]

    response = client.get("/api/v1/deepspace/chats/tasks", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 3
    assert payload[0]["id"]
    assert payload[0]["priority"] == 90
    assert payload[0]["metadata_json"]["source"] == "github"
    assert payload[1]["priority"] == 80
    assert payload[1]["metadata_json"]["source"] == "gmail"
    recurring_task = next(item for item in payload if item["id"] == recurring_id)
    assert recurring_task["is_recurring"] is True
    assert recurring_task["enabled"] is True
    assert recurring_task["automation_json"]["schedule_type"] == "daily"
    assert recurring_task["next_run_at"] is not None

    patch_response = client.patch(
        f"/api/v1/deepspace/chats/tasks/{recurring_id}",
        headers=headers,
        json={"enabled": False},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["enabled"] is False


def test_proactive_tasks_run_now_endpoint_triggers_immediate_execution(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch,
) -> None:
    seeded = seed_user(
        "Proactive Run Now Tenant",
        "runnow@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    todo_service = TodoService(db_session)
    task_id = todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Daily briefing",
        active_form="Daily briefing",
        status="pending",
        priority=75,
        is_recurring=True,
        enabled=True,
        next_run_at=datetime(2026, 5, 7, 9, 0, tzinfo=UTC),
        automation_json={
            "action_type": "agent_prompt",
            "schedule_type": "daily",
            "prompt": "Prepare a morning brief.",
            "web_search_enabled": True,
        },
    )

    called = {"value": False}

    async def _fake_run_recurring_rule(**kwargs):  # noqa: ARG001
        called["value"] = True

    monkeypatch.setattr(
        "app.deepspace.workers.tasks_proactive._run_recurring_rule", _fake_run_recurring_rule
    )

    response = client.post(
        f"/api/v1/deepspace/chats/tasks/{task_id}/run-now", headers=headers
    )

    assert response.status_code == 200
    assert called["value"] is True
    payload = response.json()
    assert payload["id"] == task_id
    assert payload["content"] == "Daily briefing"


def test_proactive_task_summary_endpoint_reports_due_and_failure_pressure(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    seeded = seed_user(
        "Proactive Summary Tenant",
        "summary@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    todo_service = TodoService(db_session)
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Urgent follow-up",
        active_form="Urgent follow-up",
        status="pending",
        priority=90,
        metadata_json={"source": "gmail"},
    )
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Recurring morning brief",
        active_form="Recurring morning brief",
        status="in_progress",
        priority=70,
        is_recurring=True,
        enabled=True,
        next_run_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
        automation_json={
            "action_type": "agent_prompt",
            "schedule_type": "daily",
            "prompt": "Prepare a morning brief.",
            "requires_approval": True,
            "source": "proactive",
        },
        metadata_json={"source": "proactive"},
    )
    todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Paused cleanup",
        active_form="Paused cleanup",
        status="completed",
        priority=10,
        is_recurring=True,
        enabled=False,
        next_run_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
        automation_json={"action_type": "agent_prompt", "schedule_type": "daily"},
        metadata_json={"source": "github"},
    )
    db_session.add(
        AgentActivity(
            tenant_id=seeded.tenant_id,
            activity_type="error",
            description="Proactive Gmail scan failed.",
            source="gmail",
            metadata_json={
                "failure_idempotency_key": "gmail-summary-failure",
                "error_code": "gmail_scan_failed",
                "proactive_cycle_id": "cycle-summary-1",
                "phase": "gmail_scan",
            },
        )
    )
    db_session.add(
        AgentActivity(
            tenant_id=seeded.tenant_id,
            activity_type="heartbeat",
            description="Proactive scan heartbeat.",
            source="proactive",
            metadata_json={
                "proactive_cycle_id": "cycle-summary-1",
                "phase": "heartbeat",
                "status": "degraded",
            },
        )
    )
    db_session.commit()

    response = client.get("/api/v1/deepspace/chats/tasks/summary", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["total"] == 3
    assert payload["pending"] == 1
    assert payload["in_progress"] == 1
    assert payload["completed"] == 1
    assert payload["recurring"] == 2
    assert payload["enabled"] == 2
    assert payload["paused"] == 1
    assert payload["due"] == 1
    assert payload["approval_required"] == 1
    assert payload["source_breakdown"]["gmail"] == 1
    assert payload["source_breakdown"]["proactive"] == 1
    assert payload["source_breakdown"]["github"] == 1
    assert payload["recent_activity_count"] >= 1
    assert payload["recent_error_count"] >= 1
    assert payload["recent_cycle_count"] == 1
    assert payload["recent_cycle_failure_count"] >= 1
    assert payload["gmail_scan_failure_count"] == 1
    assert payload["gmail_message_failure_count"] == 0
    assert payload["last_cycle_status"] == "degraded"
    assert payload["last_cycle_at"] is not None


def test_delete_task_endpoint(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    from sqlalchemy import select

    from app.deepspace.models.agent_todo import AgentTodo

    seeded = seed_user(
        "Delete Task Tenant",
        "deletetask@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    todo_service = TodoService(db_session)
    task_id = todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Temp task to delete",
        status="pending",
    )

    # Verify task exists
    tasks_before = (
        db_session.execute(
            select(AgentTodo).where(
                AgentTodo.id == task_id,
                AgentTodo.status != "deleted",
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks_before) == 1

    # Send DELETE request
    response = client.delete(
        f"/api/v1/deepspace/chats/tasks/{task_id}",
        headers=headers,
    )
    assert response.status_code == 204

    db_session.expire_all()

    # Verify task is soft-deleted
    tasks_after = (
        db_session.execute(
            select(AgentTodo).where(
                AgentTodo.id == task_id,
                AgentTodo.status != "deleted",
            )
        )
        .scalars()
        .all()
    )
    assert len(tasks_after) == 0

    # Try listing todos via service
    todos = (
        db_session.execute(select(AgentTodo).where(AgentTodo.id == task_id))
        .scalars()
        .first()
    )
    assert todos is not None
    assert todos.status == "deleted"


def test_cascade_delete_tasks_on_conversation_delete(
    client,
    db_session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    from sqlalchemy import select

    from app.deepspace.models.agent_todo import AgentTodo
    from app.query.repositories.chat import ChatRepository

    seeded = seed_user(
        "Cascade Delete Tenant",
        "cascade@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    repo = ChatRepository(db_session)
    conv = repo.create_conversation(
        tenant_id=seeded.tenant_id,
        user_id=seeded.user_id,
        title="Cascade Conversation",
        kind="deepspace",
    )

    todo_service = TodoService(db_session)
    task_id = todo_service.upsert_task(
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        content="Task to cascade delete",
        thread_id=str(conv.id),
        status="pending",
    )

    # Deleting conversation should trigger cascade delete
    delete_response = client.delete(
        f"/api/v1/deepspace/chats/{conv.id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    db_session.expire_all()

    # Verify the task's status is now "deleted"
    task = (
        db_session.execute(select(AgentTodo).where(AgentTodo.id == task_id))
        .scalars()
        .first()
    )
    assert task is not None
    assert task.status == "deleted"
