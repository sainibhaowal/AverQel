from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from app.deepspace.services.chat_service import PRODUCTIVITY_TOOLS, DeepSpaceChatService
from app.deepspace.services.runtime_policy import DeepSpaceToolPolicy
from app.deepspace.services.runtime_store import DeepSpaceRuntimeStore
from app.deepspace.services.url_reader import validate_public_url
from app.providers.services.base import ProviderRequestError


def test_deepspace_policy_blocks_ide_and_mcp_tools() -> None:
    policy = DeepSpaceToolPolicy()

    assert policy.decide("url_read", {}).allowed
    assert policy.mode("write") == "write"
    assert policy.mode("workspace_write") == "write"
    assert policy.mode("memory_search") == "read"
    assert policy.mode("memory_write") == "write"
    assert policy.mode("memory_forget") == "write"
    assert not policy.decide("terminal", {}).allowed
    assert not policy.decide("mcp_call", {}).allowed


def test_deepspace_exposes_scoped_memory_tools() -> None:
    names = {
        item["function"]["name"]
        for item in PRODUCTIVITY_TOOLS
        if isinstance(item.get("function"), dict)
    }

    assert {"memory_search", "memory_read", "memory_write", "memory_forget"}.issubset(names)
    assert "workspace_write" in names


def test_url_reader_rejects_private_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.deepspace.services.url_reader.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 80))],
    )

    with pytest.raises(ProviderRequestError, match="Private"):
        validate_public_url("http://example.test/document")


@pytest.mark.asyncio
async def test_read_only_tools_run_concurrently() -> None:
    service = object.__new__(DeepSpaceChatService)
    service.tool_policy = DeepSpaceToolPolicy()
    started: list[str] = []

    async def fake_execute(**kwargs):
        started.append(kwargs["tool_name"])
        await asyncio.sleep(0.05)
        return {"tool": kwargs["tool_name"]}

    service._execute_productivity_tool = fake_execute
    started_at = time.monotonic()
    results = await asyncio.gather(
        service._run_tool_call(
            tool_name="url_read",
            arguments={"url": "https://example.com"},
            auth=SimpleNamespace(),
            conversation_id=SimpleNamespace(),
            web_provider=None,
            web_candidate=None,
            request=None,
            loop_deadline=time.monotonic() + 5,
            run_id=None,
            read_semaphore=asyncio.Semaphore(8),
            write_lock=asyncio.Lock(),
        ),
        service._run_tool_call(
            tool_name="image_read",
            arguments={"url": "https://example.com/image.png"},
            auth=SimpleNamespace(),
            conversation_id=SimpleNamespace(),
            web_provider=None,
            web_candidate=None,
            request=None,
            loop_deadline=time.monotonic() + 5,
            run_id=None,
            read_semaphore=asyncio.Semaphore(8),
            write_lock=asyncio.Lock(),
        ),
    )

    assert time.monotonic() - started_at < 0.09
    assert started == ["url_read", "image_read"]
    assert all(result["success"] for result in results)


def test_runtime_store_bounds_retained_step_payload() -> None:
    result = DeepSpaceRuntimeStore._bounded_json({"content": "x" * 30_000})

    assert result["truncated"] is True
    assert len(str(result["preview"])) <= 19_500
