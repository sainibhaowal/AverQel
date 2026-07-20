from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.auth.dependencies import AuthContext
from app.services.deepspace.execution.agent_executor import AgentExecutor


@pytest.mark.asyncio
@pytest.mark.unit_no_db
async def test_compact_context_records_automatic_compaction_state() -> None:
    executor = AgentExecutor.__new__(AgentExecutor)
    executor.auth = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=frozenset({"member"}),
        token_id="token",
    )
    executor.settings = SimpleNamespace(max_context_chars=1000)
    executor._resolved_context_limit = 1000
    executor._last_compaction_state = None

    async def _fake_load_memory_facts(*, query: str, limit: int = 5):  # noqa: ARG001
        return []

    executor._load_memory_facts = _fake_load_memory_facts  # type: ignore[assignment]
    messages = [
        {"role": "system", "content": "system rules"},
        {"role": "user", "content": "original question"},
    ]
    for index in range(20):
        messages.append(
            {
                "role": "assistant" if index % 2 else "user",
                "content": f"message {index} " + ("payload " * 30),
            }
        )

    compacted = await executor._compact_context(messages)

    assert compacted
    assert any(
        message["role"] == "system"
        and str(message["content"]).startswith("COMPACTED HISTORY SUMMARY:")
        for message in compacted
    )
    assert executor.last_compaction_state is not None
    assert executor.last_compaction_state["trigger"] == "automatic"
    assert executor.last_compaction_state["saved_tokens"] > 0


@pytest.mark.unit_no_db
def test_auto_compaction_threshold_lives_in_80_to_85_percent_band() -> None:
    assert 0.80 <= AgentExecutor.AUTO_COMPACTION_THRESHOLD <= 0.85
