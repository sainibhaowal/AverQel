from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.auth import AuthContext
from app.services.deepspace.execution.agent_tools import ToolExecutor


def _build_executor() -> ToolExecutor:
    executor = ToolExecutor.__new__(ToolExecutor)
    executor.db = SimpleNamespace()
    executor.settings = SimpleNamespace(provider_timeout_seconds=8)
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="test-token",
    )
    executor.mode = None
    executor.memory = SimpleNamespace()
    executor.todo = SimpleNamespace()
    executor.shell = SimpleNamespace()
    executor.read_files = set()
    executor.plan_mode = False
    return executor


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_web_search_emits_progress(monkeypatch):
    progress: list[dict[str, object]] = []

    async def sink(payload: dict[str, object]) -> None:
        progress.append(payload)

    class _Provider:
        def search(self, _request):
            return SimpleNamespace(
                answer="Short answer",
                results=[
                    SimpleNamespace(
                        title="Example",
                        url="https://example.com",
                        content="Example content",
                    )
                ],
            )

    class _Registry:
        def __init__(self, _settings):
            pass

        def get_web_search_provider_from_selection(self, _candidate):
            return _Provider()

    class _SelectionService:
        def __init__(self, _db, _settings):
            pass

        def resolve_web_search(self, *args, **kwargs):
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        provider_type="tavily",
                        metadata={"search_depth": "basic"},
                    )
                ]
            )

    monkeypatch.setattr(
        "app.services.providers.registry.ProviderRegistry",
        _Registry,
    )
    monkeypatch.setattr(
        "app.services.providers.selection_service.ProviderSelectionService",
        _SelectionService,
    )

    executor = _build_executor()
    result = await executor._exec_web_search(
        {"query": "latest browser automation"},
        event_sink=sink,
    )

    assert result.success is True
    assert "Results (1 found)" in result.output
    assert [item["stream"] for item in progress] == ["system", "system", "system"]
    assert "Resolving web-search provider" in str(progress[0]["text"])
    assert "Searching live web via tavily" in str(progress[1]["text"])
    assert "Collected 1 live web results" in str(progress[2]["text"])


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_web_fetch_emits_progress(monkeypatch):
    progress: list[dict[str, object]] = []

    async def sink(payload: dict[str, object]) -> None:
        progress.append(payload)

    class _FakeResponse:
        status_code = 200
        text = "<html><body><main>Hello <b>world</b></main></body></html>"

        def raise_for_status(self):
            return None

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, _url):
            return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **_kwargs: _FakeClient())

    executor = _build_executor()
    result = await executor._exec_web_fetch(
        {"url": "https://example.com", "prompt": "Summarize"},
        event_sink=sink,
    )

    assert result.success is True
    assert "FETCHED https://example.com" in result.output
    assert len(progress) == 5
    assert "Requesting https://example.com" in str(progress[0]["text"])
    assert "Received HTTP 200" in str(progress[1]["text"])
    assert "Extracting readable text" in str(progress[2]["text"])
    assert "Prepared fetched content for prompt focus" in str(progress[3]["text"])
    assert "Extracted" in str(progress[4]["text"])


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_sync_connector_emits_progress(monkeypatch):
    progress: list[dict[str, object]] = []

    async def sink(payload: dict[str, object]) -> None:
        progress.append(payload)

    class _ExecuteResult:
        def scalars(self):
            return self

        def first(self):
            return connector

    class _FakeDb:
        def execute(self, _query):
            return _ExecuteResult()

    class _FakeOrchestrator:
        def __init__(self, _db):
            pass

        def sync_connector(self, connector_id, tenant_id, progress_callback=None):
            if callable(progress_callback):
                progress_callback(
                    {
                        "phase": "fetch",
                        "message": "Fetching source data from github.",
                        "connector_id": str(connector_id),
                    }
                )
                progress_callback(
                    {
                        "phase": "complete",
                        "message": "Sync completed for GitHub Sync.",
                        "connector_id": str(connector_id),
                    }
                )
            return {"status": "success", "message": "Sync completed."}

    monkeypatch.setattr(
        "app.services.integrations.connector_orchestrator.ConnectorOrchestrator",
        _FakeOrchestrator,
    )

    executor = _build_executor()
    connector = SimpleNamespace(
        id=uuid4(),
        name="GitHub Sync",
        tenant_id=executor.auth.tenant_id,
    )
    executor.db = _FakeDb()
    result = await executor._exec_sync_connector(
        {"connector_id": str(connector.id)},
        event_sink=sink,
    )

    assert result.success is True
    assert result.output == "Sync completed."
    assert len(progress) >= 2
    assert "Fetching source data from github." in str(progress[0]["text"])
    assert "Sync completed for GitHub Sync." in str(progress[-1]["text"])
