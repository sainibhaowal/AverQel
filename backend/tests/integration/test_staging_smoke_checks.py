from __future__ import annotations

from fastapi.testclient import TestClient


def test_staging_smoke_health_and_metrics(client: TestClient) -> None:
    live = client.get("/api/v1/health/live")
    ready = client.get("/api/v1/health/ready")
    metrics = client.get("/api/v1/metrics")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert metrics.status_code == 200
    assert "aks_api_requests_total" in metrics.text


def test_staging_smoke_error_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": "00000000-0000-0000-0000-000000000000"},
        json={"email": "nobody@example.com", "password": "bad_password_format_123!"},
    )
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_CREDENTIALS"
    assert payload["trace_id"]
