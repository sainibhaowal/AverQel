from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.errors import ApiError
from app.realtime import api as realtime_api


def test_realtime_websocket_rejects_auth_before_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = False

    class FakeSession:
        def close(self) -> None:
            nonlocal closed
            closed = True

    async def reject_auth(*_args: object, **_kwargs: object) -> None:
        raise ApiError(code="AUTH_REQUIRED", message="Authentication required.", status_code=401)

    monkeypatch.setattr(realtime_api, "SessionLocal", FakeSession)
    monkeypatch.setattr(
        realtime_api,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://unused"),
    )
    monkeypatch.setattr(realtime_api, "_authenticate_websocket_auth_context", reject_auth)

    app = FastAPI()
    app.include_router(realtime_api.router, prefix="/api/v1")

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as denied:
            with client.websocket_connect("/api/v1/realtime/ws?token=not-a-valid-token"):
                pytest.fail("Unauthenticated realtime WebSocket was accepted")

    assert denied.value.code == 1008
    assert closed
