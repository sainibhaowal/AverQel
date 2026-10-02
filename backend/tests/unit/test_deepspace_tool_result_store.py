from app.deepspace.services.tool_result_store import ToolResultStore


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)


def test_tool_result_store_is_scoped_and_opaque(monkeypatch) -> None:
    redis = _Redis()
    monkeypatch.setattr("app.deepspace.services.tool_result_store.get_redis_client", lambda: redis)
    store = ToolResultStore()

    ref = store.put(
        tenant_id="tenant-a", user_id="user-a", conversation_id="chat-a", value={"x": 1}
    )

    assert store.get(tenant_id="tenant-a", user_id="user-a", conversation_id="chat-a", ref=ref) == {
        "x": 1
    }
    assert (
        store.get(tenant_id="tenant-b", user_id="user-a", conversation_id="chat-a", ref=ref) is None
    )
    assert (
        store.get(tenant_id="tenant-a", user_id="user-a", conversation_id="chat-a", ref="x" * 129)
        is None
    )
