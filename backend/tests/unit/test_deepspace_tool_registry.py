from __future__ import annotations

import pytest

from app.deepspace.services.chat_service import NATIVE_TOOL_REGISTRY
from app.deepspace.services.tool_registry import NativeToolValidationError


def test_registry_contains_dynamic_tools_and_unifies_document_operations() -> None:
    assert NATIVE_TOOL_REGISTRY.contains("web_search")
    assert NATIVE_TOOL_REGISTRY.contains("discover_tools")
    assert NATIVE_TOOL_REGISTRY.contains("read")
    assert NATIVE_TOOL_REGISTRY.contains("analyze")
    assert not NATIVE_TOOL_REGISTRY.contains("document_read")
    assert not NATIVE_TOOL_REGISTRY.contains("document_query")
    assert not NATIVE_TOOL_REGISTRY.contains("document_compare")
    assert not NATIVE_TOOL_REGISTRY.contains("todo_read")
    assert not NATIVE_TOOL_REGISTRY.contains("todo_mark")
    assert not NATIVE_TOOL_REGISTRY.contains("todo_check")
    assert not NATIVE_TOOL_REGISTRY.contains("observe")
    assert not NATIVE_TOOL_REGISTRY.contains("final")


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
        ("todo_write", {"operation": "update", "task_id": "t1", "status": "made_up"}),
        ("read", {"target": "host_filesystem"}),
        ("todo_write", {"operation": "update", "task_id": "t1"}),
        ("analyze", {"operation": "compare_documents", "left_file_id": "only-one"}),
        ("write", {"target": "library", "unexpected": "field"}),
    ],
)
def test_registry_rejects_invalid_or_unexpected_native_arguments(
    name: str, arguments: dict[str, object]
) -> None:
    with pytest.raises(NativeToolValidationError):
        NATIVE_TOOL_REGISTRY.validate(name, arguments)


def test_unified_read_and_analyze_validate_library_operations() -> None:
    read_arguments = NATIVE_TOOL_REGISTRY.validate(
        "read",
        {"target": "library", "operation": "query", "query": "Q4 revenue", "limit": 3},
    )
    analyze_arguments = NATIVE_TOOL_REGISTRY.validate(
        "analyze",
        {"operation": "compare_documents", "file_ids": ["file-a", "file-b"]},
    )

    assert read_arguments["operation"] == "query"
    assert read_arguments["target"] == "library"
    assert analyze_arguments["file_ids"] == ["file-a", "file-b"]


def test_multi_step_plans_require_executable_task_contracts() -> None:
    with pytest.raises(NativeToolValidationError, match="success_criteria"):
        NATIVE_TOOL_REGISTRY.validate(
            "todo_write",
            {
                "operation": "replace",
                "tasks": [
                    {"id": "research", "content": "Research sources"},
                    {
                        "id": "write",
                        "content": "Write report",
                        "verification": "Inspect the report",
                    },
                ],
            },
        )

    plan = NATIVE_TOOL_REGISTRY.validate(
        "todo_write",
        {
            "operation": "replace",
            "tasks": [
                {
                    "id": "research",
                    "content": "Research sources",
                    "success_criteria": "Primary sources are recorded",
                    "verification": "Review source URLs and notes",
                },
                {
                    "id": "write",
                    "content": "Write report",
                    "success_criteria": "The report is saved",
                    "verification": "Read the saved artifact",
                    "dependencies": ["research"],
                },
            ],
        },
    )

    assert plan["tasks"][1]["dependencies"] == ["research"]


def test_todo_write_unifies_read_update_and_completion_check() -> None:
    assert NATIVE_TOOL_REGISTRY.validate("todo_write", {"operation": "read"}) == {
        "operation": "read"
    }
    update = NATIVE_TOOL_REGISTRY.validate(
        "todo_write",
        {
            "operation": "update",
            "task_id": "research",
            "status": "completed",
            "evidence": "Primary sources saved to the artifact.",
        },
    )
    assert update["status"] == "completed"
    assert (
        NATIVE_TOOL_REGISTRY.validate("todo_write", {"operation": "check"})["operation"] == "check"
    )


def test_discovery_contract_supports_catalog_then_exact_schema_selection() -> None:
    arguments = NATIVE_TOOL_REGISTRY.validate(
        "discover_tools",
        {"query": "compare the two selected reports", "tool_names": ["analyze", "read"]},
    )

    assert arguments == {
        "query": "compare the two selected reports",
        "tool_names": ["analyze", "read"],
    }

    with pytest.raises(NativeToolValidationError):
        NATIVE_TOOL_REGISTRY.validate("discover_tools", {"query": "compare reports", "limit": 3})
