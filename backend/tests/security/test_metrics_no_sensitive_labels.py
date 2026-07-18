from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_payload_does_not_include_sensitive_label_keys(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    body = response.text.lower()
    forbidden_fragments = (
        "authorization: bearer ",
        "set-cookie:",
        "aks_refresh_token=",
        "minioadmin",
        "postgres:postgres",
        "eyj",  # common JWT prefix
    )
    for fragment in forbidden_fragments:
        assert fragment not in body
