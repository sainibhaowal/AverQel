from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.auth.dependencies import AuthContext
from app.core.errors import ApiError
from app.realtime import api as realtime_api


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttl[key] = ttl

    async def eval(self, script: str, key_count: int, key: str) -> str | None:
        assert key_count == 1
        assert "GET" in script and "DEL" in script
        return self.values.pop(key, None)

    async def xread(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []

    async def aclose(self) -> None:
        return None


def _auth_context(*, permissions: frozenset[str] = frozenset({"queries:run"})) -> AuthContext:
    return AuthContext(
        user_id=uuid.UUID("0b188ba4-0120-49da-bd3e-85f24e345124"),
        tenant_id=uuid.UUID("2108d9ad-4db2-40fb-9513-9152a718f474"),
        roles=frozenset(),
        token_id="token-id-only",
        permissions=permissions,
    )


def test_realtime_ticket_is_short_lived_and_contains_scoped_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = FakeRedis()
    monkeypatch.setattr(realtime_api, "get_redis_client", lambda: redis_client)

    response = realtime_api.create_realtime_ticket(auth=_auth_context())

    ticket = response["ticket"]
    assert isinstance(ticket, str) and ticket
    assert response["expires_in_seconds"] == realtime_api.REALTIME_TICKET_TTL_SECONDS
    key = f"{realtime_api.REALTIME_TICKET_PREFIX}{ticket}"
    assert redis_client.ttl[key] == realtime_api.REALTIME_TICKET_TTL_SECONDS
    assert json.loads(redis_client.values[key]) == {
        "user_id": "0b188ba4-0120-49da-bd3e-85f24e345124",
        "tenant_id": "2108d9ad-4db2-40fb-9513-9152a718f474",
        "roles": [],
        "permissions": ["queries:run"],
        "token_id": "token-id-only",
    }


@pytest.mark.asyncio
async def test_realtime_ticket_is_consumed_once_and_keeps_user_scope() -> None:
    redis_client = FakeRedis()
    ticket = "opaque-one-use-ticket"
    redis_client.values[f"{realtime_api.REALTIME_TICKET_PREFIX}{ticket}"] = json.dumps(
        {
            "user_id": "0b188ba4-0120-49da-bd3e-85f24e345124",
            "tenant_id": "2108d9ad-4db2-40fb-9513-9152a718f474",
            "roles": [],
            "permissions": ["queries:run"],
            "token_id": "token-id-only",
        }
    )

    auth = await realtime_api._authenticate_realtime_ticket(ticket, redis_client)

    assert str(auth.user_id) == "0b188ba4-0120-49da-bd3e-85f24e345124"
    assert str(auth.tenant_id) == "2108d9ad-4db2-40fb-9513-9152a718f474"
    assert auth.permissions == frozenset({"queries:run"})
    with pytest.raises(ApiError, match="invalid or expired"):
        await realtime_api._authenticate_realtime_ticket(ticket, redis_client)


def test_realtime_ticket_cannot_be_minted_without_realtime_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = FakeRedis()
    monkeypatch.setattr(realtime_api, "get_redis_client", lambda: redis_client)

    with pytest.raises(ApiError, match="Insufficient permission"):
        realtime_api.create_realtime_ticket(auth=_auth_context(permissions=frozenset()))

    assert redis_client.values == {}


def test_realtime_ticket_connects_without_database_or_jwt_in_socket_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = FakeRedis()
    monkeypatch.setattr(realtime_api, "get_redis_client", lambda: redis_client)
    ticket_response = realtime_api.create_realtime_ticket(auth=_auth_context())
    ticket = str(ticket_response["ticket"])

    def unexpected_database_session() -> None:
        raise AssertionError("Ticket authentication must not open a database session")

    monkeypatch.setattr(realtime_api, "SessionLocal", unexpected_database_session)
    monkeypatch.setattr(
        realtime_api,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://unused"),
    )
    monkeypatch.setattr(realtime_api.aioredis, "from_url", lambda *_args, **_kwargs: redis_client)

    app = FastAPI()
    app.include_router(realtime_api.router, prefix="/api/v1")

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/realtime/ws?ticket={ticket}") as websocket:
            ready = websocket.receive_json()
            assert ready["event"] == "realtime_ready"
            assert ready["protocol"] == "averqel-realtime-v1"
            websocket.send_json({"event": "ping"})
            assert websocket.receive_json() == {"event": "pong"}

    assert f"{realtime_api.REALTIME_TICKET_PREFIX}{ticket}" not in redis_client.values
