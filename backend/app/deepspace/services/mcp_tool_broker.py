"""Private MCP catalogue broker for the DeepSpace model boundary.

The MCP bridge remains the authority for connection ownership, policy,
catalogue revisions, approvals, and remote execution.  This module only
controls what reaches the model: a small, provider-neutral search/schema/call
surface and bounded results.  The complete upstream catalogue stays in the
server-side ``DeepSpaceMCPTool`` bindings.
"""

from __future__ import annotations

import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

MCP_SEARCH_TOOLS = "mcp_search_tools"
MCP_GET_TOOL_SCHEMA = "mcp_get_tool_schema"
MCP_CALL_TOOL = "mcp_call_tool"
MCP_BROKER_TOOL_NAMES = frozenset({MCP_SEARCH_TOOLS, MCP_GET_TOOL_SCHEMA, MCP_CALL_TOOL})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: object) -> set[str]:
    return set(_TOKEN_RE.findall(str(value or "").casefold()))


def _short_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}…"


def _schema_node(node: object, *, depth: int = 0, budget: list[int]) -> Any:
    """Build a small schema hint without changing the private exact schema."""
    if not isinstance(node, dict) or depth > 4 or budget[0] <= 0:
        return {"type": "object", "description": "Additional schema details are private."}
    budget[0] -= 1
    result: dict[str, Any] = {}
    for key in ("type", "required"):
        if key in node and isinstance(node[key], str | list):
            result[key] = node[key]
    if isinstance(node.get("description"), str):
        result["description"] = _short_text(node["description"], 180)
    if isinstance(node.get("enum"), list):
        result["enum"] = [
            item for item in node["enum"][:12] if isinstance(item, str | int | float | bool)
        ]
        if len(node["enum"]) > 12:
            result["enum_truncated"] = True
    if isinstance(node.get("properties"), dict):
        properties: dict[str, Any] = {}
        for name, child in list(node["properties"].items())[:40]:
            properties[str(name)] = _schema_node(child, depth=depth + 1, budget=budget)
        result["properties"] = properties
        if len(node["properties"]) > 40:
            result["properties_truncated"] = True
    if isinstance(node.get("items"), dict):
        result["items"] = _schema_node(node["items"], depth=depth + 1, budget=budget)
    for key in ("oneOf", "anyOf"):
        variants = node.get(key)
        if isinstance(variants, list):
            result[key] = [
                _schema_node(item, depth=depth + 1, budget=budget)
                for item in variants[:8]
                if isinstance(item, dict)
            ]
            if len(variants) > 8:
                result[f"{key}_truncated"] = True
    return result or {"type": "object"}


class MCPToolBroker:
    """Expose only just-in-time MCP metadata to the model."""

    def __init__(
        self,
        *,
        max_search_results: int = 5,
        max_schema_chars: int = 6_000,
        max_result_chars: int = 12_000,
    ) -> None:
        self.max_search_results = max(1, min(int(max_search_results), 20))
        self.max_schema_chars = max(1_000, min(int(max_schema_chars), 20_000))
        self.max_result_chars = max(2_000, min(int(max_result_chars), 100_000))

    @staticmethod
    def _cursor(query: str, offset: int) -> str:
        payload = f"{sha256(query.casefold().encode('utf-8')).hexdigest()[:20]}:{offset}"
        return urlsafe_b64encode(payload.encode("ascii")).decode("ascii").rstrip("=")

    @staticmethod
    def _offset_from_cursor(query: str, cursor: str) -> int | None:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            payload = urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
            digest, raw_offset = payload.split(":", 1)
            offset = int(raw_offset)
        except (Base64Error, ValueError, UnicodeDecodeError):
            return None
        if digest != sha256(query.casefold().encode("utf-8")).hexdigest()[:20]:
            return None
        return offset if 0 <= offset <= 100_000 else None

    @staticmethod
    def definitions() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": MCP_SEARCH_TOOLS,
                    "description": (
                        "Search the user's connected MCP services for the smallest relevant tool. "
                        "This returns compact tool references only, not full schemas. Call this before "
                        "mcp_get_tool_schema when the correct connected tool is not already known."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "maxLength": 500,
                                "description": "The requested service, resource, and action in a few words.",
                            },
                            "cursor": {
                                "type": "string",
                                "maxLength": 128,
                                "description": "The next_cursor returned by a previous search page.",
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": MCP_GET_TOOL_SCHEMA,
                    "description": (
                        "Load the compact input schema for exactly one MCP tool reference returned by "
                        "mcp_search_tools. The exact private schema remains server-side for validation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_ref": {
                                "type": "string",
                                "maxLength": 128,
                                "description": "The exact tool_ref returned by mcp_search_tools.",
                            }
                        },
                        "required": ["tool_ref"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": MCP_CALL_TOOL,
                    "description": (
                        "Call exactly one connected MCP tool. Use the exact tool_ref from search and "
                        "provide only the arguments required for that tool. Read actions may run under "
                        "policy; external side effects still require the existing approval gate."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_ref": {
                                "type": "string",
                                "maxLength": 128,
                                "description": "The exact tool_ref returned by mcp_search_tools.",
                            },
                            "arguments": {
                                "type": "object",
                                "description": "Arguments matching the selected tool schema.",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["tool_ref", "arguments"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    @staticmethod
    def _binding_text(binding: Any) -> str:
        catalog = binding.catalog if isinstance(binding.catalog, dict) else {}
        schema = catalog.get("inputSchema") if isinstance(catalog.get("inputSchema"), dict) else {}
        properties_raw = schema.get("properties") if isinstance(schema, dict) else {}
        properties = properties_raw if isinstance(properties_raw, dict) else {}
        parameter_names = " ".join(str(name) for name in properties if str(name).strip())
        return " ".join(
            (
                binding.server_name,
                binding.raw_name,
                str(catalog.get("title") or ""),
                _short_text(catalog.get("description") or "", 1_000),
                parameter_names,
            )
        ).casefold()

    def search(
        self,
        bindings: Mapping[str, Any],
        query: str,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        query_text = " ".join(str(query or "").split())[:500]
        offset = 0
        if cursor:
            parsed_offset = self._offset_from_cursor(query_text, cursor)
            offset = parsed_offset if parsed_offset is not None else -1
            if offset < 0:
                return {
                    "status": "error",
                    "message": "The MCP search cursor is invalid or belongs to another query.",
                }
        terms = _tokens(query_text)
        scored: list[tuple[int, str, Any]] = []
        for exposed_name, binding in bindings.items():
            searchable = self._binding_text(binding)
            name_terms = _tokens(f"{binding.server_name} {binding.raw_name}")
            score = sum(1 for term in terms if term in searchable)
            score += 3 * sum(1 for term in terms if term in name_terms)
            if query_text.casefold() and query_text.casefold() in searchable:
                score += 8
            scored.append((score, str(exposed_name), binding))
        scored.sort(key=lambda item: (-item[0], item[1]))
        page = scored[offset : offset + self.max_search_results]
        matches = []
        for _score, exposed_name, binding in page:
            catalog = binding.catalog if isinstance(binding.catalog, dict) else {}
            schema = (
                catalog.get("inputSchema") if isinstance(catalog.get("inputSchema"), dict) else {}
            )
            properties_raw = schema.get("properties") if isinstance(schema, dict) else {}
            properties = properties_raw if isinstance(properties_raw, dict) else {}
            matches.append(
                {
                    "tool_ref": exposed_name,
                    "server": _short_text(binding.server_name, 100),
                    "tool": _short_text(binding.raw_name, 140),
                    "description": _short_text(catalog.get("description") or "MCP tool", 240),
                    "parameters": [str(name) for name in list(properties)[:30]],
                }
            )
        return {
            "status": "ok",
            "query": query_text,
            "matches": matches,
            "next_cursor": (
                self._cursor(query_text, offset + len(matches))
                if offset + len(matches) < len(scored)
                else None
            ),
            "has_more": offset + len(matches) < len(scored),
            "catalogue_hidden": True,
        }

    def resolve(
        self,
        bindings: Mapping[str, Any],
        tool_ref: str,
    ) -> Any | None:
        ref = str(tool_ref or "").strip()
        if not ref or len(ref) > 128:
            return None
        # References are intentionally exact and conversation-scoped. Never
        # resolve a guessed raw upstream name or accept a server identifier
        # supplied by the model.
        return bindings.get(ref)

    def get_schema(
        self,
        bindings: Mapping[str, Any],
        tool_ref: str,
    ) -> dict[str, Any]:
        binding = self.resolve(bindings, tool_ref)
        if binding is None:
            return {
                "status": "error",
                "message": "That MCP tool is not available in this conversation.",
            }
        catalog = binding.catalog if isinstance(binding.catalog, dict) else {}
        schema = catalog.get("inputSchema") if isinstance(catalog.get("inputSchema"), dict) else {}
        compact_schema = _schema_node(schema, budget=[180])
        result: dict[str, Any] = {
            "status": "ok",
            "tool_ref": binding.exposed_name,
            "server": _short_text(binding.server_name, 100),
            "tool": _short_text(binding.raw_name, 140),
            "description": _short_text(catalog.get("description") or "MCP tool", 500),
            "input_schema": compact_schema,
            "instructions": "Call mcp_call_tool with this tool_ref and a JSON object of arguments.",
        }
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(encoded) > self.max_schema_chars:
            compact_properties = (
                compact_schema.get("properties", {}) if isinstance(compact_schema, dict) else {}
            )
            compact_properties = compact_properties if isinstance(compact_properties, dict) else {}
            result["input_schema"] = {
                "type": "object",
                "required": (
                    compact_schema.get("required", []) if isinstance(compact_schema, dict) else []
                ),
                "properties": {
                    name: {"type": value.get("type", "unknown")}
                    for name, value in list(compact_properties.items())[:20]
                    if isinstance(value, dict)
                },
                "truncated": True,
            }
        if (
            len(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str))
            > self.max_schema_chars
        ):
            result["description"] = _short_text(result.get("description"), 160)
            result["input_schema"] = {
                "type": "object",
                "required": (
                    result.get("input_schema", {}).get("required", [])
                    if isinstance(result.get("input_schema"), dict)
                    else []
                ),
                "truncated": True,
            }
        return result

    def bound_result(self, result: Mapping[str, Any] | Any, *, max_chars: int | None = None) -> Any:
        """Bound model-facing MCP output without changing audit/raw execution data."""
        result_limit = self.max_result_chars if max_chars is None else max(128, int(max_chars))
        try:
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            encoded = json.dumps({"result": str(result)}, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) <= result_limit:
            return result
        bounded: dict[str, Any] = {
            "status": "truncated",
            "message": "The MCP result was larger than the model context budget.",
            "result_preview": "",
            "original_result_chars": len(encoded),
            "result_limit_chars": result_limit,
            "more_available": True,
        }
        preview_budget = max(0, result_limit - len(json.dumps(bounded)) - 8)
        bounded["result_preview"] = encoded[:preview_budget].rstrip()
        # Keep the envelope itself inside the configured hard boundary even
        # when unusually large metadata values are supplied.
        while len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))) > result_limit:
            preview = str(bounded["result_preview"])
            if not preview:
                break
            bounded["result_preview"] = preview[: -max(1, min(256, len(preview) // 8))]
        return bounded
