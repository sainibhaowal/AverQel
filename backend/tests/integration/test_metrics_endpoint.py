from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_required_families(client: TestClient) -> None:
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    body = response.text
    assert "aks_api_requests_total" in body
    assert "aks_api_request_latency_seconds" in body
    assert "aks_api_errors_total" in body
    assert "aks_worker_job_transitions_total" in body
    assert "aks_db_query_duration_seconds" in body
    assert "aks_db_connection_checkout_duration_seconds" in body
    assert "aks_extraction_method_total" in body
    assert "aks_extraction_fallback_total" in body
    assert "aks_extraction_low_confidence_total" in body
    assert "aks_extraction_failure_total" in body
    assert "aks_extraction_stage_duration_seconds" in body
