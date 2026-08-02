from __future__ import annotations

import anyio

from app.integrations.workers import tasks_mcp


def test_catalog_keeps_discovered_tools_when_optional_methods_fail() -> None:
    class _GoogleLikeRuntime:
        async def list_tools(self) -> list[dict[str, str]]:
            return [{"name": "search_threads"}, {"name": "get_thread"}]

        async def list_prompts(self) -> list[object]:
            raise RuntimeError("method not found")

        async def list_resources(self) -> list[object]:
            raise RuntimeError("method not found")

        async def list_resource_templates(self) -> list[object]:
            raise RuntimeError("method not found")

    catalog = anyio.run(tasks_mcp._load_catalog, _GoogleLikeRuntime())

    assert catalog == {
        "tools": [{"name": "search_threads"}, {"name": "get_thread"}],
        "prompts": [],
        "resources": [],
        "resource_templates": [],
    }
