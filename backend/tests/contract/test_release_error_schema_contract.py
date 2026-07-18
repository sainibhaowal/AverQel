from __future__ import annotations

from fastapi.testclient import TestClient


def _assert_error_schema(payload: dict[str, object]) -> None:
    assert "error" in payload
    assert "trace_id" in payload
    assert "timestamp" in payload
    error = payload["error"]
    assert isinstance(error, dict)
    assert "code" in error
    assert "message" in error
    assert "details" in error


def test_auth_error_schema_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": "00000000-0000-0000-0000-000000000000"},
        json={"email": "user@example.com", "password": "wrong_password123!"},
    )
    assert response.status_code == 401
    payload = response.json()
    _assert_error_schema(payload)
    assert payload["error"]["code"] == "INVALID_CREDENTIALS"


def test_queries_error_schema_contract(client: TestClient) -> None:
    response = client.post(
        "/api/v1/queries",
        json={"query": "test", "top_k": 5, "filters": {}},
    )
    assert response.status_code == 401
    payload = response.json()
    _assert_error_schema(payload)
