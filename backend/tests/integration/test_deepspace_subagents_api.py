from __future__ import annotations

from app.core.auth import create_access_token
from app.core.config import get_settings
from app.services.deepspace.subagents.subagent_registry import SubagentRegistry


def _auth_headers(seeded, *, roles: tuple[str, ...] = ("admin",)) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=roles,
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}"}


def test_subagent_list_and_terminate_api(client, seed_user, settings):
    seeded = seed_user("Subagent Tenant", "subagent@example.com", "secret", ("admin",))
    headers = _auth_headers(seeded)

    registry = SubagentRegistry(settings)
    run_id = "run-test-subagent-1"
    registry.register_run(
        run_id=run_id,
        tenant_id=str(seeded.tenant_id),
        user_id=str(seeded.user_id),
        subagent_type="research",
        prompt="Investigate the current connector state.",
        parent_id="parent-1",
        slot_index=1,
        status="running",
    )

    list_response = client.get("/api/v1/deepspace/chats/subagents", headers=headers)
    assert list_response.status_code == 200
    runs = list_response.json()
    assert any(run["run_id"] == run_id for run in runs)

    terminate_response = client.post(
        f"/api/v1/deepspace/chats/subagents/{run_id}/terminate",
        headers=headers,
    )
    assert terminate_response.status_code == 200
    assert terminate_response.json()["cancel_requested"] is True


def test_subagent_summary_api_reports_backend_and_lane_health(
    client,
    seed_user,
    settings,
    monkeypatch,
):
    seeded = seed_user(
        "Subagent Summary Tenant", "subagent-summary@example.com", "secret", ("admin",)
    )
    headers = _auth_headers(seeded)

    class _SummaryRegistry:
        def __init__(self, _settings=None):  # noqa: ARG002
            self._runs = [
                {
                    "run_id": "run-running",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "status": "running",
                    "slot_index": 1,
                },
                {
                    "run_id": "run-terminating",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "status": "terminating",
                    "slot_index": 2,
                },
                {
                    "run_id": "run-cancelled",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "status": "cancelled",
                    "slot_index": 3,
                },
                {
                    "run_id": "run-stale",
                    "tenant_id": str(seeded.tenant_id),
                    "user_id": str(seeded.user_id),
                    "status": "stale",
                    "slot_index": 4,
                },
            ]

        def list_runs(
            self, *, tenant_id, user_id, status=None, limit=20
        ):  # noqa: ARG002
            return list(self._runs)[:limit]

        def is_backend_available(self):
            return True

        @property
        def max_concurrency(self):
            return 4

        def get_daemon_heartbeat(self):
            return {
                "phase": "running",
                "timestamp": "2026-06-06T00:00:00Z",
                "interval_seconds": 300,
            }

    monkeypatch.setattr(
        "app.services.deepspace.subagents.subagent_registry.SubagentRegistry", _SummaryRegistry
    )

    response = client.get("/api/v1/deepspace/chats/subagents/summary", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend_available"] is True
    assert payload["max_concurrency"] == 4
    assert payload["active_count"] == 4
    assert payload["live_count"] == 2
    assert payload["running_count"] == 1
    assert payload["terminating_count"] == 1
    assert payload["cancelled_count"] == 1
    assert payload["stale_count"] == 1
    assert payload["pressure_count"] == 2
    assert payload["pressure_ratio"] == 0.5
    assert payload["daemon_heartbeat"]["phase"] == "running"
