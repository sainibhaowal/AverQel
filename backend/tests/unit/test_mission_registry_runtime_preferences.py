from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.deepspace.models.agent_runtime_preference import AgentRuntimePreference
from app.deepspace.missions.mission_registry import MissionRegistry


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(self, key, value, ex=None):  # noqa: ARG002
        self.data[str(key)] = str(value)

    def get(self, key):
        return self.data.get(str(key))

    def hset(self, key, mapping):  # noqa: ARG002
        self.data[str(key)] = mapping

    def hgetall(self, key):  # noqa: ARG002
        value = self.data.get(str(key))
        return value if isinstance(value, dict) else {}

    def expire(self, key, seconds):  # noqa: ARG002
        return True

    def zadd(self, key, mapping):  # noqa: ARG002
        return True

    def zrevrange(self, key, start, end):  # noqa: ARG002
        return []

    def exists(self, key):  # noqa: ARG002
        return False


def test_runtime_preferences_persist_in_db_and_override_redis(
    monkeypatch,
    db_session,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "app.deepspace.missions.mission_registry.get_redis_client",
        lambda: fake_redis,
    )

    tenant_id = str(uuid4())
    user_id = str(uuid4())
    conversation_id = str(uuid4())
    registry = MissionRegistry(settings=SimpleNamespace(), db=db_session)

    planner_mode = registry.set_planner_mode(
        tenant_id=tenant_id,
        user_id=user_id,
        mode="structured",
    )
    hooks_enabled = registry.set_runtime_hooks_enabled(
        tenant_id=tenant_id,
        user_id=user_id,
        enabled=False,
        conversation_id=conversation_id,
    )

    assert planner_mode == "structured"
    assert hooks_enabled == "false"

    planner_row = (
        db_session.query(AgentRuntimePreference)
        .filter_by(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=None,
            preference_key="planner_mode",
        )
        .one()
    )
    hooks_row = (
        db_session.query(AgentRuntimePreference)
        .filter_by(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            preference_key=f"runtime_hooks_enabled:{conversation_id}",
        )
        .one()
    )

    assert planner_row.preference_value == "structured"
    assert hooks_row.preference_value == "false"

    fake_redis.data.clear()
    fresh_registry = MissionRegistry(settings=SimpleNamespace(), db=db_session)
    assert (
        fresh_registry.get_planner_mode(tenant_id=tenant_id, user_id=user_id)
        == "structured"
    )
    assert (
        fresh_registry.get_runtime_hooks_enabled(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        is False
    )


def test_runtime_preferences_fall_back_to_settings_defaults(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "app.deepspace.missions.mission_registry.get_redis_client",
        lambda: fake_redis,
    )

    settings = SimpleNamespace(
        deepspace_default_planner_mode="structured",
        deepspace_default_subagent_profile="analysis",
        deepspace_runtime_hooks_enabled=False,
        deepspace_workspace_mode_enabled=True,
    )
    registry = MissionRegistry(settings=settings, db=None)

    assert (
        registry.get_planner_mode(tenant_id=str(uuid4()), user_id=str(uuid4()))
        == "structured"
    )
    assert (
        registry.get_subagent_profile(tenant_id=str(uuid4()), user_id=str(uuid4()))
        == "analysis"
    )
    assert (
        registry.get_runtime_hooks_enabled(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
        )
        is False
    )
    assert (
        registry.get_workspace_mode_enabled(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
        )
        is True
    )


def test_runtime_preferences_normalize_unknown_values_to_safe_defaults(
    monkeypatch,
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "app.deepspace.missions.mission_registry.get_redis_client",
        lambda: fake_redis,
    )

    registry = MissionRegistry(settings=SimpleNamespace(), db=None)

    assert (
        registry.set_runtime_preference(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            preference_key=registry.PLANNER_MODE_PREF_KEY,
            value="unexpected",
        )
        == "default"
    )
    assert (
        registry.set_runtime_preference(
            tenant_id=str(uuid4()),
            user_id=str(uuid4()),
            preference_key=registry.RUNTIME_HOOKS_ENABLED_PREF_KEY,
            value="unexpected",
        )
        == "false"
    )


def test_runtime_preferences_return_all_defined_defaults(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "app.deepspace.missions.mission_registry.get_redis_client",
        lambda: fake_redis,
    )

    registry = MissionRegistry(settings=SimpleNamespace(), db=None)
    preferences = registry.get_runtime_preferences(
        tenant_id=str(uuid4()),
        user_id=str(uuid4()),
    )

    assert preferences["execution_mode"] == "auto_review"
    assert preferences["planner_mode"] == "default"
    assert preferences["subagent_profile"] == "default"
    assert preferences["runtime_hooks_enabled"] == "true"
    assert preferences["workspace_mode_enabled"] == "true"
