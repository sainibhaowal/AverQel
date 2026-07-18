from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_live_health_endpoint() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("X-Trace-Id")
