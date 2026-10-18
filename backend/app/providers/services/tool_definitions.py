"""Provider-neutral safeguards for model-facing function definitions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def unique_tool_definitions(tools: Iterable[object] | None) -> list[dict[str, Any]]:
    """Return the first valid definition for each function name.

    OpenAI-compatible, Anthropic, Gemini, and local runtimes all reject a
    request when two function definitions have the same name.  DeepSpace
    dynamically combines native and connected-service definitions, so this is
    a transport boundary invariant rather than a provider-specific detail.
    Keeping the first definition preserves the deterministic caller order and
    avoids silently changing which authorized schema wins after a collision.
    """

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_tool in tools or ():
        if not isinstance(raw_tool, dict):
            continue
        function = raw_tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str):
            continue
        normalized_name = name.strip()
        if not normalized_name or normalized_name in seen:
            continue
        seen.add(normalized_name)
        # Keep the request immutable while ensuring providers receive the same
        # canonical name that was used for collision detection.
        normalized_tool = dict(raw_tool)
        normalized_function = dict(function)
        normalized_function["name"] = normalized_name
        normalized_tool["function"] = normalized_function
        result.append(normalized_tool)
    return result
