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
    assert policy.mode("workspace_write") is None
    assert policy.mode("memory_search") is None
    assert policy.mode("memory_read") is None
    assert policy.mode("memory_write") is None
    assert policy.mode("memory_forget") is None
    assert not policy.decide("workspace_write", {}).allowed
    assert not policy.decide("memory_search", {}).allowed
    assert not policy.decide("terminal", {}).allowed
    assert not policy.decide("mcp_call", {}).allowed


def test_deepspace_exposes_universal_workspace_tools() -> None:
    names = {
        item["function"]["name"]
        for item in PRODUCTIVITY_TOOLS
        if isinstance(item.get("function"), dict)
    }

    assert {"read", "find", "write", "edit", "delete"}.issubset(names)
    assert "save" not in names
    assert "workspace_write" not in names
    assert "memory_search" not in names


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


@pytest.mark.asyncio
async def test_provider_retry_retries_pre_output_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(DeepSpaceChatService)
    attempts = 0

    async def stream_factory():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderRequestError("test", 503, "temporary")
        yield {"type": "delta", "text": "ok"}

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.deepspace.services.chat_service.asyncio.sleep", no_sleep)
    frames = [
        item
        async for item in service._provider_stream_with_retry(
            stream_factory,
            run_id=None,
            deadline=time.monotonic() + 5,
            provider_type="lmstudio",
        )
    ]

    assert attempts == 2
    assert frames == [{"type": "delta", "text": "ok"}]


@pytest.mark.asyncio
async def test_provider_retry_does_not_duplicate_partial_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(DeepSpaceChatService)

    async def stream_factory():
        yield {"type": "delta", "text": "partial"}
        raise ProviderRequestError("test", 502, "connection lost")

    monkeypatch.setattr("app.deepspace.services.chat_service.asyncio.sleep", lambda _: None)
    with pytest.raises(ProviderRequestError):
        [
            item
            async for item in service._provider_stream_with_retry(
                stream_factory, run_id=None, deadline=time.monotonic() + 5
            )
        ]


def test_context_budget_reports_thresholds_and_safe_remaining() -> None:
    state = DeepSpaceChatService._context_budget_state(
        used_tokens=195,
        context_limit=200,
        reserved_output_tokens=20,
        compacted=False,
    )

    assert state["contextStatus"] == "emergency"
    assert state["safeRemainingTokens"] == 0

    unknown = DeepSpaceChatService._context_budget_state(
        used_tokens=10,
        context_limit=None,
        reserved_output_tokens=20,
        compacted=False,
    )
    assert unknown["contextStatus"] == "unknown"
    assert unknown["safeRemainingTokens"] is None


def test_context_history_fit_preserves_system_and_newest_messages() -> None:
    messages = [{"role": "system", "content": "rules"}]
    messages.extend({"role": "user", "content": "x" * 300} for _ in range(12))

    fitted, compacted = DeepSpaceChatService._fit_history_to_context(
        messages, context_window=700, max_output_tokens=256
    )

    assert compacted is True
    assert fitted[0]["role"] == "system"
    assert fitted[-1] == messages[-1]
