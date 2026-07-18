from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from scripts.smoke_connectors import (
    CONNECTOR_NAME_PREFIX,
    ConnectorSmokeOptions,
    ConnectorSmokeRunner,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> Any:
        return self._payload


class _FakeSmokeApiClient:
    def __init__(self) -> None:
        now = datetime.now(tz=UTC)
        self.integrations = {
            slug: {
                "id": f"{slug}-integration-id",
                "name": slug.replace("-", " ").title(),
                "slug": slug,
                "description": f"{slug} integration",
                "ui_metadata": {},
                "is_active": True,
                "oauth_status": {
                    "configured": True,
                    "message": f"{slug} OAuth client ready.",
                    "missing": [],
                    "provider_key": slug,
                },
            }
            for slug in (
                "google-drive",
                "gmail",
                "google-calendar",
                "github",
                "slack",
                "notion",
            )
        }
        self.connectors: list[dict[str, Any]] = []
        self._oauth_pending: dict[str, int] = {}
        self._sync_pending: dict[str, int] = {}
        self.calls: list[tuple[str, str]] = []
        self._clock = now

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:  # noqa: ARG002
        self.calls.append(("GET", url))
        self._advance_state()
        if url == "/api/v1/integrations":
            return _FakeResponse(200, list(self.integrations.values()))
        if url == "/api/v1/integrations/connectors":
            return _FakeResponse(
                200,
                [self._render_connector(connector) for connector in self.connectors],
            )
        return _FakeResponse(404, {"detail": "not found"})

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("POST", url))
        payload = kwargs.get("json") or {}
        if url == "/api/v1/integrations/connectors":
            connector = {
                "id": f"connector-{len(self.connectors) + 1}",
                "tenant_id": "tenant-1",
                "user_id": "user-1",
                "integration_id": payload["integration_id"],
                "name": payload["name"],
                "status": "active",
                "config": payload.get("config") or {},
                "sync_frequency": payload.get("sync_frequency") or "daily",
                "last_sync_at": None,
                "next_sync_at": None,
                "last_error": None,
                "error_count": 0,
                "created_at": self._clock.isoformat().replace("+00:00", "Z"),
                "updated_at": self._clock.isoformat().replace("+00:00", "Z"),
            }
            self.connectors.append(connector)
            return _FakeResponse(200, self._render_connector(connector))
        if url.endswith("/oauth/start"):
            connector_id = url.split("/")[-3]
            self._oauth_pending[connector_id] = 1
            return _FakeResponse(
                200,
                {
                    "available": True,
                    "authorization_url": f"https://auth.example.test/{connector_id}",
                    "message": "OAuth flow initialized.",
                    "connector_id": connector_id,
                },
            )
        if url.endswith("/sync"):
            connector_id = url.split("/")[-2]
            self._sync_pending[connector_id] = 1
            connector = self._find_connector(connector_id)
            connector["status"] = "syncing"
            connector["updated_at"] = self._tick()
            return _FakeResponse(200, {"status": "accepted", "message": "queued"})
        return _FakeResponse(404, {"detail": "not found"})

    def _find_connector(self, connector_id: str) -> dict[str, Any]:
        for connector in self.connectors:
            if connector["id"] == connector_id:
                return connector
        raise AssertionError(f"unknown connector {connector_id}")

    def _advance_state(self) -> None:
        for connector_id, remaining in list(self._oauth_pending.items()):
            if remaining <= 0:
                connector = self._find_connector(connector_id)
                connector["config"] = {
                    **connector["config"],
                    "auth_mode": "mcp",
                    "mcp_tools": ["tool-a", "tool-b"],
                }
                connector["updated_at"] = self._tick()
                del self._oauth_pending[connector_id]
            else:
                self._oauth_pending[connector_id] = remaining - 1
        for connector_id, remaining in list(self._sync_pending.items()):
            if remaining <= 0:
                connector = self._find_connector(connector_id)
                connector["status"] = "active"
                connector["health_status"] = "healthy"
                connector["last_error"] = None
                connector["error_count"] = 0
                connector["last_sync_at"] = self._tick()
                connector["circuit_open_until"] = None
                connector["config"] = {
                    **connector["config"],
                    "health": {
                        "status": "healthy",
                        "healthy": True,
                        "last_checked_at": self._tick(),
                        "last_good_at": self._tick(),
                        "circuit_open_until": None,
                        "consecutive_failures": 0,
                        "metadata": {"source": "smoke"},
                    },
                }
                connector["updated_at"] = self._tick()
                del self._sync_pending[connector_id]
            else:
                self._sync_pending[connector_id] = remaining - 1

    def _tick(self) -> str:
        self._clock = self._clock + timedelta(seconds=1)
        return self._clock.isoformat().replace("+00:00", "Z")

    def _render_connector(self, connector: dict[str, Any]) -> dict[str, Any]:
        health = connector.get("config", {}).get("health") or {}
        return {
            **connector,
            "health_status": health.get("status")
            or connector.get("health_status")
            or "healthy",
            "last_checked_at": health.get("last_checked_at"),
            "last_good_at": health.get("last_good_at"),
            "circuit_open_until": health.get("circuit_open_until"),
            "consecutive_failures": health.get("consecutive_failures") or 0,
            "health_metadata": health.get("metadata") or {},
            "last_success_snapshot": connector.get("config", {}).get(
                "last_success_snapshot"
            ),
        }


def test_smoke_runner_creates_selects_and_verifies_provider_flows() -> None:
    client = _FakeSmokeApiClient()
    options = ConnectorSmokeOptions(
        base_url="https://averqel.localhost",
        access_token="smoke-token",
        providers=("google-drive", "github"),
        poll_interval_seconds=0.0,
        oauth_timeout_seconds=5,
        sync_timeout_seconds=5,
    )
    runner = ConnectorSmokeRunner(client, options)

    payload = runner.run()

    assert payload["status"] == "success"
    assert [item["provider"] for item in payload["providers"]] == [
        "google-drive",
        "github",
    ]
    assert all(item["oauth_completed"] is True for item in payload["providers"])
    assert all(item["sync_completed"] is True for item in payload["providers"])
    assert all(item["last_sync_at"] for item in payload["providers"])
    assert all(item["circuit_open_until"] is None for item in payload["providers"])
    assert all(
        item["authorization_url"].startswith("https://auth.example.test/")
        for item in payload["providers"]
    )
    assert all(
        item["connector_name"].startswith(CONNECTOR_NAME_PREFIX)
        for item in payload["providers"]
    )
    assert client.calls.count(("POST", "/api/v1/integrations/connectors")) == 2
    assert (
        client.calls.count(
            ("POST", "/api/v1/integrations/connectors/connector-1/oauth/start")
        )
        == 1
    )
    assert (
        client.calls.count(
            ("POST", "/api/v1/integrations/connectors/connector-2/oauth/start")
        )
        == 1
    )


def test_smoke_runner_is_idempotent_for_existing_connectors() -> None:
    client = _FakeSmokeApiClient()
    options = ConnectorSmokeOptions(
        base_url="https://averqel.localhost",
        access_token="smoke-token",
        providers=("slack",),
        poll_interval_seconds=0.0,
        oauth_timeout_seconds=5,
        sync_timeout_seconds=5,
    )
    runner = ConnectorSmokeRunner(client, options)

    first = runner.run()
    second = runner.run()

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert client.calls.count(("POST", "/api/v1/integrations/connectors")) == 1
