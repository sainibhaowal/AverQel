from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select, text

from app.db.session import get_session_factory, set_db_tenant_context
from app.query.models.query import Query
from app.system.services.rate_limit_service import RateLimitService
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def test_query_rate_limit_exceeded_returns_429_and_does_not_persist_query(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    seeded = seed_user(
        "tenant-rate-limit",
        "reader-rate-limit@tenant.example",
        "StrongPass!1234",
        ("reader",),
    )
    token = _login(client, seeded)

    def fake_increment(
        self: RateLimitService, *, key: str, window_seconds: int
    ) -> tuple[int, int]:
        del window_seconds
        if "queries_user" in key:
            return 61, 60
        return 1, 300

    monkeypatch.setattr(RateLimitService, "_increment_counter", fake_increment)

    response = client.post(
        "/api/v1/queries",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
        json={"query": "rate limit check", "top_k": 5, "filters": {}},
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    session = get_session_factory()()
    try:
        session.execute(text("SET ROLE aks_app"))
        set_db_tenant_context(session, seeded.tenant_id)
        query_count = session.execute(
            select(func.count())
            .select_from(Query)
            .where(Query.tenant_id == seeded.tenant_id)
        ).scalar_one()
        assert query_count == 0
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
