from __future__ import annotations

import json
from typing import Any

import pytest

from app.providers.services.anthropic_provider import AnthropicProvider
from app.providers.services.base import ProviderRequestError
from app.providers.services.google_provider import GoogleProvider
from app.providers.services.types import ChatGenerateRequest

TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}


def _request(**overrides: Any) -> ChatGenerateRequest:
    values: dict[str, Any] = {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "Use tools when needed."},
            {"role": "user", "content": "Find current news."},
        ],
        "temperature": 0,
        "max_tokens": 256,
        "base_url": "https://provider.example/v1",
        "api_key": "test-key",
        "tools": [TOOL],
        "tool_choice": "required",
    }
    values.update(overrides)
    return ChatGenerateRequest(**values)


def test_google_builds_native_function_declarations() -> None:
    payload = GoogleProvider._build_payload(_request())

    declaration = payload["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "web_search"
    assert declaration["parameters"]["required"] == ["query"]
    assert declaration["parameters"]["type"] == "OBJECT"
    assert payload["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    assert payload["systemInstruction"]["parts"][0]["text"] == "Use tools when needed."


def test_google_strips_openai_only_schema_keywords_recursively() -> None:
    request = _request(
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "todo_write",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "content": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 1000,
                                        }
                                    },
                                },
                            }
                        },
                    },
                },
            }
        ]
    )

    parameters = GoogleProvider._build_payload(request)["tools"][0]["functionDeclarations"][0][
        "parameters"
    ]
    assert parameters["type"] == "OBJECT"
    assert "additionalProperties" not in parameters
    assert parameters["properties"]["tasks"]["type"] == "ARRAY"
    assert parameters["properties"]["tasks"]["items"]["type"] == "OBJECT"
    assert "additionalProperties" not in parameters["properties"]["tasks"]["items"]
    assert "minLength" not in parameters["properties"]["tasks"]["items"]["properties"]["content"]


def test_google_stream_error_reads_and_preserves_provider_message() -> None:
    class Response:
        status_code = 400

        def json(self) -> dict[str, Any]:
            raise AssertionError("streaming errors must use the already-read body")

        @property
        def text(self) -> str:
            raise AssertionError("streaming response text must not be accessed before read")

    with pytest.raises(ProviderRequestError, match="Invalid tool schema"):
        GoogleProvider._raise_provider_error(
            Response(), b'{"error":{"message":"Invalid tool schema"}}'
        )


def test_google_converts_tool_history_to_function_response() -> None:
    request = _request(
        messages=[
            {"role": "user", "content": "Find current news."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "thought_signature": "sig-123",
                        "function": {"name": "web_search", "arguments": '{"query":"news"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": '{"results":[]}'},
        ]
    )
    _system, contents = GoogleProvider._build_contents(request.messages)

    assert contents[1]["parts"][0]["thoughtSignature"] == "sig-123"
    assert contents[-1]["parts"][0]["functionResponse"]["name"] == "web_search"
    assert contents[-1]["parts"][0]["functionResponse"]["response"] == {"results": []}


def test_google_extracts_native_function_call() -> None:
    text, thinking, calls = GoogleProvider._extract_candidate_parts(
        {
            "content": {
                "parts": [
                    {
                        "functionCall": {"name": "web_search", "args": {"query": "news"}},
                        "thoughtSignature": "sig-123",
                    }
                ]
            }
        }
    )

    assert text == ""
    assert thinking is None
    assert calls[0]["function"]["name"] == "web_search"
    assert json.loads(calls[0]["function"]["arguments"]) == {"query": "news"}
    assert calls[0]["thought_signature"] == "sig-123"


def test_anthropic_translates_tools_and_tool_history() -> None:
    request = _request(
        messages=[
            {"role": "user", "content": "Find current news."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "toolu-1",
                        "type": "function",
                        "function": {"name": "web_search", "arguments": '{"query":"news"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "toolu-1", "content": '{"results":[]}'},
        ]
    )
    system, messages = AnthropicProvider._system_and_messages(request.messages)

    assert system is None
    assert messages[1]["content"][0]["type"] == "tool_use"
    assert messages[2]["content"][0]["type"] == "tool_result"
    assert messages[2]["content"][0]["tool_use_id"] == "toolu-1"
    assert AnthropicProvider._tools_payload(request)[0]["input_schema"]["required"] == ["query"]


def test_anthropic_extracts_tool_use_response() -> None:
    text, thinking, calls = AnthropicProvider._extract_text_blocks(
        [{"type": "tool_use", "id": "toolu-1", "name": "web_search", "input": {"query": "news"}}]
    )

    assert text == ""
    assert thinking is None
    assert calls[0]["id"] == "toolu-1"
    assert json.loads(calls[0]["function"]["arguments"]) == {"query": "news"}
