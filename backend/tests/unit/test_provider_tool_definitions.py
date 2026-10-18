from __future__ import annotations

from app.providers.services.tool_definitions import unique_tool_definitions


def test_unique_tool_definitions_keeps_first_definition_and_order() -> None:
    first = {"type": "function", "function": {"name": " web_search ", "description": "first"}}
    duplicate = {
        "type": "function",
        "function": {"name": "web_search", "description": "second"},
    }
    second = {"type": "function", "function": {"name": "url_read"}}

    normalized = unique_tool_definitions([first, duplicate, None, {}, second])

    assert [item["function"]["name"] for item in normalized] == ["web_search", "url_read"]
    assert first["function"]["name"] == " web_search "
