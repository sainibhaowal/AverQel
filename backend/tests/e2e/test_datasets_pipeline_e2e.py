import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.conftest import SeededUser
from tests.support.datasets import ensure_test_datasets

DATASET_ROOT = Path(__file__).parent.parent.parent.parent / "Docs" / "Datasets"


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_dataset_upload_index_query_citation_e2e(
    client: TestClient,
    seed_user,
    settings: Settings,
):
    ensure_test_datasets()
    seeded_user = seed_user("tenant-e2e", "e2e@example.com", "Password!123", ("editor",))
    token = _login(client, seeded_user)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded_user.tenant_id),
        "Idempotency-Key": str(uuid.uuid4()),
    }

    test_file_path = DATASET_ROOT / "clean" / "clean_sample.txt"
    with open(test_file_path, "rb") as f:
        file_payload = f.read()

    # 1. Upload
    response = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": (test_file_path.name, file_payload, "text/plain")},
    )
    if response.status_code != 200:
        pytest.fail(f"Upload failed: {response.status_code} - {response.text}")

    data = response.json()
    document_id = data["document_id"]

    # 2. Poll for Indexed Status
    status = "queued"
    max_attempts = 30
    attempts = 0
    while (
        status in ("queued", "downloading", "parsing", "chunking", "embedding")
        and attempts < max_attempts
    ):
        time.sleep(1)
        res = client.get(f"/api/v1/documents/{document_id}/status", headers=headers)
        assert res.status_code == 200
        status = res.json()["status"]
        if status == "dead_lettered":
            pytest.fail(f"Document became dead lettered: {res.json()}")
        attempts += 1

    assert status == "indexed", f"Document failed to index, final status: {status}"

    # 3. Query
    query_payload = {"query": "ALPHA-CLEAN-001", "top_k": 5}
    q_res = client.post("/api/v1/queries", headers=headers, json=query_payload)

    if q_res.status_code != 200:
        pytest.fail(f"Query returned {q_res.status_code}: {q_res.text}")

    q_data = q_res.json()

    # 4. Citation Assertion
    citations = q_data.get("citations", [])
    assert (
        len(citations) > 0
    ), f"No citations returned for query 'ALPHA-CLEAN-001'. Answer: {q_data.get('answer')}"

    matched_doc = any(cit["document_id"] == document_id for cit in citations)
    assert matched_doc, "Citation did not match the newly uploaded dataset file."
