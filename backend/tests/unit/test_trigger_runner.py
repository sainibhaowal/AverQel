from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.deepspace.proactive.trigger_runner import build_trigger_runner


class _FakeTodoService:
    def __init__(self):
        self.marked: list[dict[str, object]] = []
        self.upserted: list[dict[str, object]] = []

    def mark_task_run(self, **kwargs):
        self.marked.append(kwargs)

    def upsert_task(self, **kwargs):
        self.upserted.append(kwargs)


class _FakeMissionRegistry:
    def __init__(self, settings, db=None):  # noqa: ARG002
        pass

    def get_execution_mode(self, **kwargs):  # noqa: ARG002
        return "auto_review"


class _FailingOrchestrator:
    def __init__(self, **kwargs):  # noqa: ARG002
        raise AssertionError(
            "orchestrator should not be created for approval-only rules"
        )


@pytest.mark.asyncio
async def test_trigger_runner_handles_recurring_approval_without_orchestrator() -> None:
    todo_service = _FakeTodoService()
    notifications: list[dict[str, object]] = []
    db = SimpleNamespace(
        add=lambda _item: None,
        execute=lambda *_args, **_kwargs: None,
    )
    rule = SimpleNamespace(
        id="rule-1",
        tenant_id=uuid4(),
        user_id=uuid4(),
        content="Delete old drafts",
        automation_json={
            "action_type": "delete",
            "requires_approval": True,
            "schedule_type": "daily",
        },
    )
    runner = build_trigger_runner(
        db=db,
        settings=SimpleNamespace(),
        todo_service=todo_service,
        mission_registry_cls=_FakeMissionRegistry,
        orchestrator_cls=_FailingOrchestrator,
        build_runtime=lambda _config: None,
        notify_proactive=lambda **kwargs: notifications.append(kwargs),
    )

    result = await runner.run_recurring_rule(rule=rule, cycle_id="cycle-1")

    assert result.status == "pending"
    assert notifications
    assert todo_service.marked[-1]["status"] == "pending"


def test_trigger_runner_next_run_for_interval_rule() -> None:
    todo_service = _FakeTodoService()
    runner = build_trigger_runner(
        db=SimpleNamespace(),
        settings=SimpleNamespace(),
        todo_service=todo_service,
        mission_registry_cls=_FakeMissionRegistry,
        orchestrator_cls=lambda **kwargs: None,
        build_runtime=lambda _config: None,
        notify_proactive=lambda **kwargs: None,
    )
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    rule = SimpleNamespace(
        automation_json={
            "schedule_type": "interval",
            "interval_minutes": 45,
        }
    )

    next_run = runner.next_run_for_rule(rule, now=now)

    assert next_run == datetime(2026, 6, 13, 12, 45, tzinfo=UTC)
