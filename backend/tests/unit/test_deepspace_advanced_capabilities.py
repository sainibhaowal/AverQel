from types import SimpleNamespace

import pytest

from app.deepspace.services.chat_service import PRODUCTIVITY_TOOLS
from app.deepspace.services.sandbox_executor import SandboxExecutorError, execute_sandbox


def test_advanced_native_tools_are_provider_neutral() -> None:
    names = {item["function"]["name"] for item in PRODUCTIVITY_TOOLS}
    assert {"sandbox_execute", "document_read", "document_compare"} <= names


@pytest.mark.asyncio
async def test_sandbox_is_disabled_by_default() -> None:
    settings = SimpleNamespace(deepspace_sandbox_enabled=False)
    with pytest.raises(SandboxExecutorError, match="not enabled"):
        await execute_sandbox(code="print(1)", language="python", settings=settings)


@pytest.mark.asyncio
async def test_sandbox_rejects_unsupported_language_before_network() -> None:
    settings = SimpleNamespace(
        deepspace_sandbox_enabled=True, deepspace_sandbox_url="http://invalid"
    )
    with pytest.raises(SandboxExecutorError, match="Only Python"):
        await execute_sandbox(code="select 1", language="javascript", settings=settings)
