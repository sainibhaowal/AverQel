"""Just-in-time discovery for DeepSpace's native tool catalogue.

The model first sees the compact descriptions of this request's authorized
capabilities, then chooses exact names whose full schemas should be loaded.
That keeps schema tokens low without using brittle keyword routing. Execution
still passes through the normal typed registry, policy, and scoped handlers.
"""

from __future__ import annotations

from typing import Any

from app.deepspace.services.tool_registry import ToolRegistry

DISCOVER_TOOLS_NAME = "discover_tools"
MAX_DISCOVERED_TOOLS = 8
MAX_CATALOG_TOOLS = 40

DISCOVER_TOOLS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": DISCOVER_TOOLS_NAME,
        "description": (
            "Discover native DeepSpace capabilities in two steps. First call with a natural-language "
            "query and no tool_names to receive the compact catalog of authorized capabilities. "
            "Then call again with the exact name or names selected from that catalog in tool_names; "
            "their full schemas become callable on the next turn. Do not guess names. A direct "
            "conversational answer needs no discovery."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 1000,
                    "description": "The capability or next action needed, stated naturally.",
                },
                "tool_names": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 80},
                    "minItems": 1,
                    "maxItems": MAX_DISCOVERED_TOOLS,
                    "description": (
                        "On the second call, exact capability names copied from the returned catalog. "
                        "Omit this on the first call."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


class NativeToolBroker:
    """Expose a compact catalog and load only exact request-authorized schemas."""

    def discover(
        self,
        *,
        query: str,
        registry: ToolRegistry,
        allowed_names: set[str],
        tool_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """List authorized tools or load explicitly selected schemas.

        ``allowed_names`` is assembled by the chat runtime for this request.
        The broker cannot load a name outside that set, even if a provider
        invents one or a future registry entry is added without exposure.
        """

        normalized_query = " ".join(str(query or "").split())[:1000]
        authorized_names = sorted(
            name
            for name in allowed_names
            if name != DISCOVER_TOOLS_NAME and registry.contains(name)
        )
        if tool_names is None:
            catalog = [
                {
                    "name": name,
                    "description": registry.spec(name).description[:160],
                }
                for name in authorized_names[:MAX_CATALOG_TOOLS]
            ]
            return {
                "status": "catalog",
                "requested_capability": normalized_query,
                "available_tools": catalog,
                "catalog_truncated": len(authorized_names) > MAX_CATALOG_TOOLS,
                "message": (
                    "Choose the exact capability names from available_tools, then call "
                    "discover_tools again with those names in tool_names. No schema was loaded "
                    "or action executed yet."
                ),
            }

        requested_names = list(dict.fromkeys(str(name).strip() for name in tool_names))
        invalid_names = [
            name
            for name in requested_names
            if name not in allowed_names or not registry.contains(name)
        ]
        if invalid_names:
            return {
                "status": "invalid_selection",
                "loaded_tools": [],
                "invalid_names": invalid_names[:MAX_DISCOVERED_TOOLS],
                "message": (
                    "One or more names are not in this request's authorized native catalog. "
                    "Review the catalog and select exact names from it."
                ),
            }
        if len(requested_names) > MAX_DISCOVERED_TOOLS:
            return {
                "status": "selection_too_large",
                "loaded_tools": [],
                "message": f"Select no more than {MAX_DISCOVERED_TOOLS} tools for one step.",
            }

        return {
            "status": "loaded",
            "loaded_tools": [
                {
                    "name": name,
                    "description": registry.spec(name).description[:240],
                }
                for name in requested_names
            ],
            "message": "The selected tool schemas are available on the next provider round.",
        }
