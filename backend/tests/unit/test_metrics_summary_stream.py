from __future__ import annotations

import asyncio
import json

import pytest

from app.system.api import metrics as metrics_api
from app.system.services import metrics_service

pytestmark = pytest.mark.unit_no_db


class FakeAsyncRedis:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.closed = False

    async def hsetnx(self, _key: str, field: str, value: str) -> int:
        if field in self.values:
            return 0
        self.values[field] = value
        return 1

    async def hgetall(self, _key: str) -> dict[str, str]:
        return dict(self.values)

    async def aclose(self) -> None:
        self.closed = True


class FakePubSub:
    def __init__(self, on_message=None) -> None:
        self.closed = False
        self.on_message = on_message

    async def get_message(self, **_kwargs: object) -> None:
        if self.on_message is not None:
            self.on_message()
            self.on_message = None
        return None

    async def aclose(self) -> None:
        self.closed = True


def test_metrics_stream_sends_initial_snapshot_and_closes_connections(
    monkeypatch,
) -> None:
    client = FakeAsyncRedis({"api_requests_total": "12"})
    pubsub = FakePubSub()
    monkeypatch.setattr(metrics_api, "METRICS_STREAM_MAX_SECONDS", 0)

    async def collect_first_event() -> str:
        stream = metrics_api._stream_metrics_snapshots(
            client=client,  # type: ignore[arg-type]
            pubsub=pubsub,  # type: ignore[arg-type]
            initial_snapshot={
                "api_requests_total": 12,
                "metrics_scope": "service-wide",
                "metrics_complete": True,
                "metrics_started_at": "2026-10-18T00:00:00+00:00",
                "snapshot_at": "2026-10-18T00:00:01+00:00",
            },
        )
        first_event = await anext(stream)
        await stream.aclose()
        return first_event

    first_event = asyncio.run(collect_first_event())
    payload = json.loads(first_event.split("data: ", maxsplit=1)[1])

    assert first_event.startswith("event: metrics\n")
    assert payload["api_requests_total"] == 12
    assert payload["metrics_scope"] == "service-wide"
    assert client.closed is True
    assert pubsub.closed is True


def test_metrics_stream_sends_a_new_snapshot_after_a_shared_counter_changes(
    monkeypatch,
) -> None:
    client = FakeAsyncRedis(
        {
            "api_requests_total": "12",
            "meta:started_at": "2026-10-18T00:00:00+00:00",
            "meta:complete": "1",
        }
    )
    pubsub = FakePubSub(on_message=lambda: client.values.__setitem__("api_requests_total", "13"))
    monkeypatch.setattr(metrics_api, "METRICS_STREAM_MAX_SECONDS", 10)
    monkeypatch.setattr(metrics_api, "METRICS_STREAM_SNAPSHOT_SECONDS", 0)
    monkeypatch.setattr(metrics_api, "METRICS_STREAM_HEARTBEAT_SECONDS", 60)

    async def collect_initial_and_changed_events() -> tuple[str, str]:
        stream = metrics_api._stream_metrics_snapshots(
            client=client,  # type: ignore[arg-type]
            pubsub=pubsub,  # type: ignore[arg-type]
            initial_snapshot=metrics_service._build_runtime_metrics_summary(client.values),
        )
        initial_event = await anext(stream)
        changed_event = await anext(stream)
        await stream.aclose()
        return initial_event, changed_event

    initial_event, changed_event = asyncio.run(collect_initial_and_changed_events())

    initial_payload = json.loads(initial_event.split("data: ", maxsplit=1)[1])
    changed_payload = json.loads(changed_event.split("data: ", maxsplit=1)[1])
    assert initial_payload["api_requests_total"] == 12
    assert changed_payload["api_requests_total"] == 13
    assert client.closed is True
    assert pubsub.closed is True
