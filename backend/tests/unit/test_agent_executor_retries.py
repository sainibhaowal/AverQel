from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.deepspace.execution.agent_executor import AgentExecutor
from app.providers.services.base import ProviderRequestError
from app.providers.services.types import ChatGenerateRequest, ChatGenerateResponse


class MockSettings:
    def __init__(self):
        self.max_context_chars = 100000
        self.llm_model = "test-model"
        self.llm_provider = "openai"
        self.llm_api_base_url = "http://localhost:8000"
        self.llm_api_key = "test-key"
        self.provider_timeout_seconds = 1.0
        self.deepspace_agent_max_steps = 12


class MockLLM:
    def __init__(self):
        self.generate = MagicMock()
        self.stream_generate_events = MagicMock()


@pytest.mark.asyncio
async def test_generate_with_retry_success_after_failure(monkeypatch):
    settings = MockSettings()
    db = MagicMock()
    auth = MagicMock()
    auth.tenant_id = "test-tenant"
    auth.user_id = "test-user"

    executor = AgentExecutor(db=db, auth=auth, settings=settings)
    mock_llm = MockLLM()
    executor._resolved_llm = mock_llm

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ProviderRequestError(
                provider_name="test", status_code=429, message="Rate limit"
            )
        return ChatGenerateResponse(
            content="Success response", thinking_content=None, usage={}
        )

    mock_llm.generate.side_effect = side_effect
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    request = ChatGenerateRequest(
        model="test-model",
        messages=[],
        temperature=0.1,
        max_tokens=100,
        base_url="http://localhost:8000",
        api_key="test-key",
    )

    res = await executor._generate_with_retry(request)
    assert res.content == "Success response"
    assert call_count == 2


@pytest.mark.asyncio
async def test_generate_with_retry_exhausted(monkeypatch):
    settings = MockSettings()
    db = MagicMock()
    auth = MagicMock()
    auth.tenant_id = "test-tenant"
    auth.user_id = "test-user"

    executor = AgentExecutor(db=db, auth=auth, settings=settings)
    mock_llm = MockLLM()
    executor._resolved_llm = mock_llm

    def side_effect(*args, **kwargs):
        raise ProviderRequestError(
            provider_name="test", status_code=429, message="Rate limit"
        )

    mock_llm.generate.side_effect = side_effect
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    request = ChatGenerateRequest(
        model="test-model",
        messages=[],
        temperature=0.1,
        max_tokens=100,
        base_url="http://localhost:8000",
        api_key="test-key",
    )

    with pytest.raises(ProviderRequestError) as exc:
        await executor._generate_with_retry(request)
    assert exc.value.status_code == 429
    assert mock_llm.generate.call_count == 6


@pytest.mark.asyncio
async def test_stream_llm_events_retry_success(monkeypatch):
    settings = MockSettings()
    db = MagicMock()
    auth = MagicMock()
    auth.tenant_id = "test-tenant"
    auth.user_id = "test-user"

    executor = AgentExecutor(db=db, auth=auth, settings=settings)
    mock_llm = MockLLM()
    executor._resolved_llm = mock_llm

    stream_call_count = 0

    async def mock_stream_success():
        yield {"type": "delta", "text": "token"}

    def mock_stream_fail_then_success(*args, **kwargs):
        nonlocal stream_call_count
        stream_call_count += 1
        if stream_call_count == 1:

            async def failing_stream():
                raise ProviderRequestError(
                    provider_name="test", status_code=429, message="Rate limit"
                )
                yield

            return failing_stream()
        return mock_stream_success()

    mock_llm.stream_generate_events.side_effect = mock_stream_fail_then_success
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    request = ChatGenerateRequest(
        model="test-model",
        messages=[],
        temperature=0.1,
        max_tokens=100,
        base_url="http://localhost:8000",
        api_key="test-key",
    )

    events = []
    async for event in executor._stream_llm_events_with_timeout(request):
        events.append(event)

    assert len(events) == 1
    assert events[0]["text"] == "token"
    assert stream_call_count == 2
