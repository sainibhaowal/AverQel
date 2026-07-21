from __future__ import annotations

from types import SimpleNamespace

from app.system.services.cache_service import QueryCacheService


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.raise_on_get = False
        self.raise_on_set = False

    def get(self, key: str) -> object:
        if self.raise_on_get:
            raise RuntimeError("redis down")
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        _ = ttl
        if self.raise_on_set:
            raise RuntimeError("redis down")
        self.values[key] = value


def test_query_cache_get_and_set_paths(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.system.services.cache_service.get_redis_client", lambda: fake
    )

    service = QueryCacheService()
    assert service.get("missing") is None

    fake.values["bytes"] = b'{"ok": true}'
    assert service.get("bytes") == {"ok": True}

    fake.values["bad-json"] = "{not-json"
    assert service.get("bad-json") is None

    fake.values["not-dict"] = '["a"]'
    assert service.get("not-dict") is None

    fake.values["not-string"] = SimpleNamespace()
    assert service.get("not-string") is None

    service.set(key="k1", value={"a": 1}, ttl_seconds=5)
    assert isinstance(fake.values["k1"], str)


def test_query_cache_handles_redis_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.system.services.cache_service.get_redis_client", lambda: fake
    )
    service = QueryCacheService()

    fake.raise_on_get = True
    assert service.get("k") is None

    fake.raise_on_get = False
    fake.raise_on_set = True
    service.set(key="k", value={"a": 1}, ttl_seconds=1)
