from __future__ import annotations

import pytest

from app.deepspace.services.chat_service import NATIVE_TOOL_REGISTRY, PRODUCTIVITY_TOOLS
from app.deepspace.services.tool_registry import NativeToolValidationError


def test_registry_covers_every_exposed_native_productivity_tool() -> None:
    emitted_names = {item["function"]["name"] for item in PRODUCTIVITY_TOOLS}

    assert emitted_names <= NATIVE_TOOL_REGISTRY.names()
    assert NATIVE_TOOL_REGISTRY.contains("web_search")
    assert NATIVE_TOOL_REGISTRY.contains("document_compare")


def test_registry_emission_is_defensive_and_schema_versioned() -> None:
    first = NATIVE_TOOL_REGISTRY.emit("web_search")
    second = NATIVE_TOOL_REGISTRY.emit("web_search")

    first["function"]["parameters"]["properties"]["query"]["maxLength"] = 1

    assert second["function"]["parameters"]["properties"]["query"]["maxLength"] == 512
    assert len(NATIVE_TOOL_REGISTRY.spec("web_search").schema_digest) == 24


def test_registry_normalizes_valid_arguments_without_extra_fields() -> None:
    arguments = NATIVE_TOOL_REGISTRY.validate(
        "web_search", {"query": "provider caching", "max_results": 4}
    )

    assert arguments == {"query": "provider caching", "max_results": 4}


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("web_search", {"query": "x"}),
        ("sandbox_execute", {"language": "bash", "code": "echo unsafe"}),
        ("todo_mark", {"task_id": "t1", "status": "made_up"}),
        ("read", {"target": "host_filesystem"}),
        ("document_compare", {"left_file_id": "only-one"}),
        ("write", {"target": "library", "unexpected": "field"}),
    ],
)
def test_registry_rejects_invalid_or_unexpected_native_arguments(
    name: str, arguments: dict[str, object]
) -> None:
    with pytest.raises(NativeToolValidationError):
        NATIVE_TOOL_REGISTRY.validate(name, arguments)
