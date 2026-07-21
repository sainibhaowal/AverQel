from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.deepspace.subagents.subagent_registry as subagent_registry_module
from app.auth.dependencies import AuthContext
from app.core.config import get_settings
from app.deepspace.execution.agent_tools import ToolResult
from app.deepspace.subagents.subagent_manager import (
    SubagentManager,
    _LocalSubagentRegistry,
)
from app.deepspace.subagents.subagent_registry import SubagentRegistry


class _BusyRegistry:
    def acquire_slot(self, **_kwargs):
        return None


class _CancelRegistry:
    def __init__(self):
        self.completed: list[dict[str, object]] = []
        self.released: list[dict[str, object]] = []

    def acquire_slot(self, **_kwargs):
        return 1

    def register_run(self, **kwargs):
        return kwargs

    def is_cancel_requested(self, _run_id):
        return True

    def touch_run(self, *_args, **_kwargs):
        return None

    def complete_run(self, **kwargs):
        self.completed.append(kwargs)
        return kwargs

    def release_slot(self, **kwargs):
        self.released.append(kwargs)


class _MidFlightCancelRegistry:
    def __init__(self):
        self.completed: list[dict[str, object]] = []
        self.released: list[dict[str, object]] = []
        self.cancel_requested = False

    def acquire_slot(self, **_kwargs):
        return 1

    def register_run(self, **kwargs):
        return kwargs

    def is_cancel_requested(self, _run_id):
        return self.cancel_requested

    def request_termination(self, _run_id):
        self.cancel_requested = True
        return {"status": "terminating"}

    def touch_run(self, *_args, **_kwargs):
        return None

    def complete_run(self, **kwargs):
        self.completed.append(kwargs)
        return kwargs

    def release_slot(self, **kwargs):
        self.released.append(kwargs)


class _FailingRedis:
    def hset(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def expire(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def set(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def get(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def exists(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def zadd(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def zrevrange(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    def hgetall(self, *_args, **_kwargs):
        raise RuntimeError("redis unavailable")


class _FlakyAcquireRedis(_FailingRedis):
    def ping(self):
        return True

    def exists(self, *_args, **_kwargs):
        return True

    def set(self, *_args, **_kwargs):
        raise RuntimeError("redis slot acquire failed")


class _SlotRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expirations: dict[str, int] = {}

    def set(self, key, value, nx=False, ex=None):  # type: ignore[no-untyped-def]
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        if ex is not None:
            self.expirations[key] = int(ex)
        return True

    def get(self, key):  # type: ignore[no-untyped-def]
        return self.values.get(key)

    def delete(self, key):  # type: ignore[no-untyped-def]
        self.values.pop(key, None)
        self.hashes.pop(key, None)

    def hset(self, key, mapping):  # type: ignore[no-untyped-def]
        current = self.hashes.setdefault(key, {})
        current.update({str(k): str(v) for k, v in mapping.items()})

    def expire(self, key, ex):  # type: ignore[no-untyped-def]
        self.expirations[key] = int(ex)

    def hgetall(self, key):  # type: ignore[no-untyped-def]
        return dict(self.hashes.get(key, {}))

    def zadd(self, *_args, **_kwargs):
        return None

    def zrevrange(self, *_args, **_kwargs):
        return []

    def exists(self, key):  # type: ignore[no-untyped-def]
        return key in self.values


class _SlowAgentExecutor:
    def __init__(self, *_args, **_kwargs):
        pass

    async def stream_agent_loop(self, *_args, **_kwargs):
        await asyncio.sleep(0.05)
        if False:  # pragma: no cover - keeps this an async generator
            yield None


class _ProfileAwareAgentExecutor:
    last_init: dict[str, object] = {}
    last_stream: dict[str, object] = {}

    def __init__(self, *_args, **kwargs):
        self.__class__.last_init = dict(kwargs)

    async def stream_agent_loop(self, *_args, **kwargs):
        self.__class__.last_stream = dict(kwargs)
        yield SimpleNamespace(
            type="answer_delta",
            data={"text": "Collected evidence. "},
        )
        yield SimpleNamespace(
            type="final_answer",
            data={"content": "Verified answer from the research lane."},
        )


class _SummaryOnlyAgentExecutor:
    def __init__(self, *_args, **_kwargs):
        pass

    async def stream_agent_loop(self, *_args, **_kwargs):
        yield SimpleNamespace(
            type="step_summary",
            data={"message": "Investigated the repo and found the likely cause."},
        )


def _manager(registry) -> SubagentManager:
    manager = SubagentManager.__new__(SubagentManager)
    manager.db = SimpleNamespace()
    manager.settings = get_settings()
    manager.auth = AuthContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        roles=frozenset({"admin"}),
        token_id="subagent-reliability-test",
    )
    manager.registry = registry
    return manager


@pytest.mark.asyncio
async def test_subagent_manager_rejects_when_parallel_slots_are_busy():
    manager = _manager(_BusyRegistry())

    result = await manager.spawn_and_execute(
        stype="research",
        prompt="Research connector failures.",
        parent_id=uuid4(),
    )

    assert not result.success
    assert "lanes are busy" in result.output


@pytest.mark.asyncio
async def test_subagent_manager_records_cancelled_status_and_releases_slot():
    registry = _CancelRegistry()
    manager = _manager(registry)

    async def _fake_loop(**_kwargs):
        await asyncio.sleep(0)
        return ToolResult(success=True, output="completed but cancellation requested")

    manager._run_subagent_loop = _fake_loop

    result = await manager.spawn_and_execute(
        stype="research",
        prompt="Research connector failures.",
        parent_id=uuid4(),
    )

    assert not result.success
    assert "cancelled" in result.output.lower()
    assert registry.completed[-1]["status"] == "cancelled"
    assert registry.released


@pytest.mark.asyncio
async def test_subagent_manager_handles_midflight_cancellation_and_releases_slot():
    registry = _MidFlightCancelRegistry()
    manager = _manager(registry)

    async def _fake_loop(*, control, **_kwargs):
        await asyncio.sleep(0)
        control.registry.request_termination(control.run_id)
        await asyncio.sleep(0)
        return ToolResult(success=True, output="completed but cancellation requested")

    manager._run_subagent_loop = _fake_loop

    result = await manager.spawn_and_execute(
        stype="research",
        prompt="Research connector failures.",
        parent_id=uuid4(),
    )

    assert not result.success
    assert "cancelled" in result.output.lower()
    assert registry.completed[-1]["status"] == "cancelled"
    assert registry.released


def test_subagent_registry_degrades_safely_when_redis_is_unavailable():
    registry = SubagentRegistry.__new__(SubagentRegistry)
    registry.settings = get_settings()
    registry.redis = _FailingRedis()

    assert registry.acquire_slot(tenant_id="t", user_id="u", run_id="r") is None
    assert registry.get_run("r") is None
    assert registry.list_runs(tenant_id="t", user_id="u") == []
    assert registry.is_cancel_requested("r") is False
    registry.record_daemon_heartbeat(phase="running")
    assert registry.get_daemon_heartbeat() is None


def test_local_subagent_registry_enforces_parallel_pressure():
    settings = SimpleNamespace(deepspace_subagent_max_concurrency=1)
    registry = _LocalSubagentRegistry(settings)

    first_slot = registry.acquire_slot(
        tenant_id="tenant-a", user_id="user-a", run_id="run-1"
    )
    second_slot = registry.acquire_slot(
        tenant_id="tenant-a", user_id="user-a", run_id="run-2"
    )

    assert first_slot == 1
    assert second_slot is None

    registry.register_run(
        run_id="run-1",
        tenant_id="tenant-a",
        user_id="user-a",
        subagent_type="research",
        prompt="Research connector failures.",
        parent_id="parent-1",
        slot_index=first_slot,
    )
    registry.complete_run(
        run_id="run-1",
        status="cancelled",
        summary="Sub-agent cancelled.",
        final_output="Sub-agent cancelled.",
    )
    registry.release_slot(
        tenant_id="tenant-a",
        user_id="user-a",
        slot_index=first_slot,
        run_id="run-1",
    )

    third_slot = registry.acquire_slot(
        tenant_id="tenant-a", user_id="user-a", run_id="run-3"
    )
    assert third_slot == 1


def test_subagent_registry_reclaims_stale_slots_during_acquire(monkeypatch):
    registry = SubagentRegistry.__new__(SubagentRegistry)
    registry.settings = SimpleNamespace(
        deepspace_subagent_max_concurrency=1,
        deepspace_subagent_lock_ttl_seconds=60,
        deepspace_subagent_run_ttl_seconds=3600,
        deepspace_subagent_stale_heartbeat_seconds=60,
        deepspace_proactive_daemon_interval_seconds=300,
    )
    registry.redis = _SlotRedis()

    tenant_id = "tenant-stale"
    user_id = "user-stale"
    stale_run_id = "stale-run"
    slot_key = registry._slot_key(tenant_id, user_id, 1)
    run_key = registry._run_key(stale_run_id)
    stale_ts = (
        (datetime.now(tz=UTC) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    )

    registry.redis.values[slot_key] = stale_run_id
    registry.redis.hashes[run_key] = {
        "run_id": stale_run_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "status": "running",
        "slot_index": "1",
        "created_at": stale_ts,
        "started_at": stale_ts,
        "updated_at": stale_ts,
        "completed_at": "",
        "cancel_requested": "0",
        "last_event_type": "start",
        "last_event_message": "Sub-agent registered.",
        "summary": "",
        "final_output": "",
        "error": "",
        "step_count": "0",
        "duration_ms": "0",
        "last_tool_name": "",
        "last_tool_id": "",
        "last_tool_output": "",
        "heartbeat_at": stale_ts,
    }
    reaped = {"count": 0}

    monkeypatch.setattr(
        subagent_registry_module,
        "increment_subagent_stale_slot_reaped",
        lambda: reaped.__setitem__("count", reaped["count"] + 1),
    )

    acquired = registry.acquire_slot(
        tenant_id=tenant_id,
        user_id=user_id,
        run_id="fresh-run",
    )

    assert acquired == 1
    assert registry.redis.values[slot_key] == "fresh-run"
    stale_run = registry.get_run(stale_run_id)
    assert stale_run is not None
    assert stale_run["status"] == "stale"
    assert stale_run["last_event_type"] == "stale_reaped"
    assert reaped["count"] == 1


@pytest.mark.asyncio
async def test_subagent_manager_uses_local_fallback_when_redis_is_unavailable():
    registry = SubagentRegistry.__new__(SubagentRegistry)
    registry.settings = get_settings()
    registry.redis = _FailingRedis()
    manager = _manager(registry)

    async def _fake_loop(**_kwargs):
        await asyncio.sleep(0)
        return ToolResult(success=True, output="fallback completed")

    manager._run_subagent_loop = _fake_loop

    result = await manager.spawn_and_execute(
        stype="research",
        prompt="Research connector failures.",
        parent_id=uuid4(),
    )

    assert result.success
    assert "fallback completed" in result.output


@pytest.mark.asyncio
async def test_subagent_manager_falls_back_when_backend_probe_passes_but_slot_acquire_fails():
    registry = SubagentRegistry.__new__(SubagentRegistry)
    registry.settings = get_settings()
    registry.redis = _FlakyAcquireRedis()
    registry._backend_error = False
    manager = _manager(registry)

    async def _fake_loop(**_kwargs):
        await asyncio.sleep(0)
        return ToolResult(success=True, output="slot fallback completed")

    manager._run_subagent_loop = _fake_loop

    result = await manager.spawn_and_execute(
        stype="research",
        prompt="Research connector failures.",
        parent_id=uuid4(),
    )

    assert result.success
    assert "slot fallback completed" in result.output


@pytest.mark.asyncio
async def test_subagent_loop_times_out_and_reports_failure(monkeypatch):
    registry = _MidFlightCancelRegistry()
    manager = _manager(registry)
    manager._subagent_timeout_seconds = lambda: 0.01  # type: ignore[method-assign]
    monkeypatch.setattr(
        "app.deepspace.execution.agent_executor.AgentExecutor",
        _SlowAgentExecutor,
    )

    result = await manager.spawn_and_execute(
        stype="research",
        prompt="Research connector failures.",
        parent_id=uuid4(),
    )

    assert not result.success
    assert "timed out" in result.output.lower()
    assert registry.completed[-1]["status"] == "failed"
    assert registry.released
    assert "timed out" in str(registry.completed[-1].get("summary", "")).lower()


@pytest.mark.asyncio
async def test_subagent_loop_routes_aliases_into_canonical_profiles(monkeypatch):
    registry = _MidFlightCancelRegistry()
    manager = _manager(registry)
    monkeypatch.setattr(
        "app.deepspace.execution.agent_executor.AgentExecutor",
        _ProfileAwareAgentExecutor,
    )

    result = await manager.spawn_and_execute(
        stype="explorer",
        prompt="Research the current MCP integration behavior.",
        parent_id=uuid4(),
    )

    assert result.success
    assert "[RESEARCH]" in result.output
    assert result.data["subagent_type"] == "research"
    assert result.data["requested_subagent_type"] == "explorer"
    assert _ProfileAwareAgentExecutor.last_init["restricted_tools"] == [
        "web_search",
        "web_fetch",
        "memory_search",
        "read_file",
        "view_file_paginated",
        "grep_search_limited",
        "directory_summary_tree",
        "task",
    ]
    assert _ProfileAwareAgentExecutor.last_stream["web_search_enabled"] is True
    assert "SUBAGENT PROFILE: Research Explorer" in str(
        _ProfileAwareAgentExecutor.last_stream["user_message"]
    )


@pytest.mark.asyncio
async def test_subagent_loop_normalizes_summary_when_no_final_answer(monkeypatch):
    registry = _MidFlightCancelRegistry()
    manager = _manager(registry)
    monkeypatch.setattr(
        "app.deepspace.execution.agent_executor.AgentExecutor",
        _SummaryOnlyAgentExecutor,
    )

    result = await manager.spawn_and_execute(
        stype="planner",
        prompt="Plan the implementation sequence for the connector refactor.",
        parent_id=uuid4(),
    )

    assert result.success
    assert "[PLANNER]" in result.output
    assert "likely cause" in result.output
    assert result.data["subagent_type"] == "planner"


@pytest.mark.asyncio
async def test_subagent_manager_uses_preferred_profile_for_generic_requests(
    monkeypatch,
):
    registry = _MidFlightCancelRegistry()
    manager = _manager(registry)
    manager.settings.deepspace_subagent_profiles_rollout_enabled = True
    monkeypatch.setattr(
        "app.deepspace.execution.agent_executor.AgentExecutor",
        _ProfileAwareAgentExecutor,
    )
    monkeypatch.setattr(
        "app.deepspace.subagents.subagent_manager.MissionRegistry.get_subagent_profile",
        lambda self, **kwargs: "planner",  # noqa: ARG005
    )

    result = await manager.spawn_and_execute(
        stype="general-purpose",
        prompt="Figure out the best plan for this connector migration.",
        parent_id=uuid4(),
    )

    assert result.success
    assert result.data["requested_subagent_type"] == "general-purpose"
    assert result.data["resolved_subagent_type"] == "planner"
