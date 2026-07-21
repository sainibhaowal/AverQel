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


def test_execution_mode_persists_in_db_and_overrides_redis(
    monkeypatch, db_session
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "app.deepspace.missions.mission_registry.get_redis_client", lambda: fake_redis
    )

    tenant_id = str(uuid4())
    user_id = str(uuid4())
    conversation_id = str(uuid4())
    registry = MissionRegistry(settings=SimpleNamespace(), db=db_session)

    mode = registry.set_execution_mode(
        tenant_id=tenant_id,
        user_id=user_id,
        mode="full_access",
    )
    assert mode == "full_access"

    row = (
        db_session.query(AgentRuntimePreference)
        .filter_by(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=None,
            preference_key="execution_mode",
        )
        .one()
    )
    assert row.preference_value == "full_access"

    # Simulate Redis loss; the persisted preference row should still win.
    fake_redis.data.clear()
    fresh_registry = MissionRegistry(settings=SimpleNamespace(), db=db_session)
    assert (
        fresh_registry.get_execution_mode(tenant_id=tenant_id, user_id=user_id)
        == "full_access"
    )

    registry.set_execution_mode(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        mode="auto_review",
    )
    assert (
        fresh_registry.get_execution_mode(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        == "auto_review"
    )
