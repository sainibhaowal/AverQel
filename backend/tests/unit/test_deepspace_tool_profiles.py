import pytest

from app.deepspace.services.chat_service import DISCOVER_TOOLS_TOOL, NATIVE_TOOL_REGISTRY
from app.deepspace.services.native_tool_broker import NativeToolBroker

pytestmark = pytest.mark.unit_no_db


def _names(items: list[dict]) -> set[str]:
    return {str(item["name"]) for item in items}


def test_initial_native_tool_surface_is_one_small_discovery_schema() -> None:
    assert DISCOVER_TOOLS_TOOL["function"]["name"] == "discover_tools"
    assert len(str(DISCOVER_TOOLS_TOOL)) < 1_500


def test_native_discovery_lists_compact_request_authorized_catalog() -> None:
    broker = NativeToolBroker()

    result = broker.discover(
        query="Search current web sources and read the official pages",
        registry=NATIVE_TOOL_REGISTRY,
        allowed_names={"web_search", "url_read", "write", "delete"},
    )

    assert result["status"] == "catalog"
    assert {item["name"] for item in result["available_tools"]} == {
        "web_search",
        "url_read",
        "write",
        "delete",
    }
    assert result["catalog_truncated"] is False
    assert (
        result["requested_capability"] == "Search current web sources and read the official pages"
    )


def test_native_discovery_loads_only_exact_selected_request_authorized_schemas() -> None:
    broker = NativeToolBroker()

    result = broker.discover(
        query="Delete a Library document",
        registry=NATIVE_TOOL_REGISTRY,
        allowed_names={"read", "find"},
        tool_names=["read"],
    )

    assert result["status"] == "loaded"
    assert _names(result["loaded_tools"]) == {"read"}


def test_native_discovery_rejects_a_name_outside_the_authorized_catalog() -> None:
    broker = NativeToolBroker()

    result = broker.discover(
        query="Delete a Library document",
        registry=NATIVE_TOOL_REGISTRY,
        allowed_names={"read", "find"},
        tool_names=["delete"],
    )

    assert result["status"] == "invalid_selection"
    assert result["loaded_tools"] == []
    assert result["invalid_names"] == ["delete"]


def test_native_catalog_does_not_depend_on_keyword_matching_and_is_deterministic() -> None:
    broker = NativeToolBroker()
    allowlist = {"web_search", "url_read", "read", "analyze", "artifact_create"}

    first = broker.discover(
        query="florbulate zaa", registry=NATIVE_TOOL_REGISTRY, allowed_names=allowlist
    )
    second = broker.discover(
        query="a completely different intent",
        registry=NATIVE_TOOL_REGISTRY,
        allowed_names=allowlist,
    )

    assert first["status"] == "catalog"
    assert _names(first["available_tools"]) == allowlist
    assert first["available_tools"] == second["available_tools"]


def test_native_tool_selection_is_bounded_to_eight_schemas() -> None:
    broker = NativeToolBroker()
    allowlist = set(NATIVE_TOOL_REGISTRY.names()) - {"discover_tools"}

    result = broker.discover(
        query="load the entire tool set",
        registry=NATIVE_TOOL_REGISTRY,
        allowed_names=allowlist,
        tool_names=sorted(allowlist)[:9],
    )

    assert result["status"] == "selection_too_large"
    assert result["loaded_tools"] == []


def test_rolling_history_keeps_recent_turns_and_bounded_reference_digest() -> None:
    from app.deepspace.services.chat_service import DeepSpaceChatService

    history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"turn {index} " * 100}
        for index in range(10)
    ]

    compacted, did_compact = DeepSpaceChatService._compact_history_for_request(history)

    assert did_compact is True
    assert compacted[0]["role"] == "system"
    assert "reference only" in compacted[0]["content"]
    assert compacted[-6:] == history[-6:]


def test_visible_token_count_excludes_system_and_request_wrappers() -> None:
    from app.deepspace.services.chat_service import DeepSpaceChatService

    assert (
        DeepSpaceChatService._estimate_visible_tokens(
            [
                {"role": "system", "content": "hidden policy " * 100},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Hello there"},
            ]
        )
        == 3
    )


def test_durable_summary_is_bounded_and_explicitly_reference_only() -> None:
    from app.deepspace.services.chat_service import DeepSpaceChatService

    summary, payload = DeepSpaceChatService._structured_history_summary(
        [
            {"role": "user", "content": "Please compare inventory.csv with archive.xlsx"},
            {
                "role": "assistant",
                "content": "I will compare the supplied files after reading them.",
            },
        ]
    )

    assert "reference only" in summary.casefold()
    assert payload["authority"] == "reference_only"
    assert payload["references"] == ["inventory.csv", "archive.xlsx"]
