from __future__ import annotations

import json
from types import SimpleNamespace

from app.deepspace.services.mcp_tool_broker import (
    MCP_BROKER_TOOL_NAMES,
    MCP_CALL_TOOL,
    MCP_GET_TOOL_SCHEMA,
    MCP_SEARCH_TOOLS,
    MCPToolBroker,
)


def _binding(name: str, *, description: str = "Read a record") -> SimpleNamespace:
    return SimpleNamespace(
        exposed_name=f"mcp_server_{name}",
        raw_name=name,
        server_name="Example MCP",
        catalog={
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text"},
                    "limit": {"type": "integer", "enum": list(range(30))},
                },
                "required": ["query"],
            },
        },
    )


def test_broker_exposes_only_three_small_model_tools() -> None:
    definitions = MCPToolBroker.definitions()
    names = {item["function"]["name"] for item in definitions}

    assert names == set(MCP_BROKER_TOOL_NAMES)
    assert len(definitions) == 3
    assert all(len(json.dumps(item)) < 2_000 for item in definitions)
    assert MCP_CALL_TOOL in names
    assert MCP_GET_TOOL_SCHEMA in names
    assert MCP_SEARCH_TOOLS in names


def test_search_returns_references_without_full_input_schema() -> None:
    broker = MCPToolBroker()
    bindings = {
        "mcp_server_search_records": _binding("search_records", description="Search records"),
        "mcp_server_create_record": _binding("create_record", description="Create a record"),
    }

    result = broker.search(bindings, "search records")

    assert result["status"] == "ok"
    assert result["matches"][0]["tool"] == "search_records"
    assert "inputSchema" not in json.dumps(result)
    assert result["matches"][0]["tool_ref"] == "mcp_server_search_records"


def test_search_cursor_is_opaque_and_query_bound() -> None:
    broker = MCPToolBroker(max_search_results=1)
    bindings = {f"tool_{index}": _binding(f"read_{index}") for index in range(3)}

    first = broker.search(bindings, "read")
    second = broker.search(bindings, "read", cursor=first["next_cursor"])
    invalid = broker.search(bindings, "write", cursor=first["next_cursor"])

    assert first["has_more"] is True
    assert len(second["matches"]) == 1
    assert second["matches"][0]["tool"] != first["matches"][0]["tool"]
    assert invalid["status"] == "error"


def test_schema_is_compact_and_result_is_bounded() -> None:
    broker = MCPToolBroker(max_schema_chars=1_000, max_result_chars=2_000)
    binding = _binding("large_tool", description="x" * 10_000)
    bindings = {binding.exposed_name: binding}

    schema = broker.get_schema(bindings, binding.exposed_name)
    oversized = broker.bound_result({"content": "x" * 20_000})

    assert schema["status"] == "ok"
    assert len(json.dumps(schema)) <= 1_000 or schema["input_schema"]["truncated"] is True
    assert oversized["status"] == "truncated"
    assert oversized["more_available"] is True
    assert len(json.dumps(oversized, separators=(",", ":"))) <= 2_000


def test_resolve_rejects_ambiguous_raw_name() -> None:
    broker = MCPToolBroker()
    first = _binding("read")
    second = _binding("read")
    second.server_name = "Other MCP"
    bindings = {"first": first, "second": second}

    assert broker.resolve(bindings, "first") is first
    assert broker.resolve(bindings, "read") is None
    assert broker.resolve(bindings, "missing") is None


def test_resolve_does_not_accept_raw_upstream_name() -> None:
    broker = MCPToolBroker()
    binding = _binding("read")

    assert broker.resolve({binding.exposed_name: binding}, "read") is None
