from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.integrations.workers import tasks_mcp_catalog


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        _ = (exc_type, exc, traceback)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.unit_no_db
def test_catalog_worker_commits_the_idempotent_catalog_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession()

    class _Service:
        def __init__(self, received_session: _FakeSession) -> None:
            assert received_session is session

        def sync_official_providers(self) -> SimpleNamespace:
            return SimpleNamespace(
                as_dict=lambda: {"created": 6, "updated": 0, "unchanged": 0, "total": 6}
            )

    monkeypatch.setattr(tasks_mcp_catalog, "SessionLocal", lambda: session)
    monkeypatch.setattr(tasks_mcp_catalog, "MCPCatalogService", _Service)

    assert tasks_mcp_catalog.sync_official_mcp_catalog.run() == {
        "created": 6,
        "updated": 0,
        "unchanged": 0,
        "total": 6,
    }
    assert session.committed is True
    assert session.rolled_back is False


@pytest.mark.unit_no_db
def test_catalog_worker_rolls_back_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession()

    class _FailingService:
        def __init__(self, received_session: _FakeSession) -> None:
            assert received_session is session

        def sync_official_providers(self) -> SimpleNamespace:
            raise RuntimeError("catalog failure")

    monkeypatch.setattr(tasks_mcp_catalog, "SessionLocal", lambda: session)
    monkeypatch.setattr(tasks_mcp_catalog, "MCPCatalogService", _FailingService)

    with pytest.raises(RuntimeError, match="catalog failure"):
        tasks_mcp_catalog.sync_official_mcp_catalog.run()

    assert session.committed is False
    assert session.rolled_back is True
