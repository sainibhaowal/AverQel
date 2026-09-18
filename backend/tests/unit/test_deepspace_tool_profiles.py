from app.deepspace.services.chat_service import PRODUCTIVITY_TOOLS, DeepSpaceChatService


def _names(tools: list[dict]) -> set[str]:
    return {str(tool["function"]["name"]) for tool in tools}


def test_greeting_profile_has_no_native_tools() -> None:
    tools, profile = DeepSpaceChatService._productivity_tools_for_prompt(
        "Hello", PRODUCTIVITY_TOOLS
    )

    assert profile == "direct"
    assert tools == []


def test_library_profile_keeps_document_capabilities_without_mutation_tools() -> None:
    tools, profile = DeepSpaceChatService._productivity_tools_for_prompt(
        "Compare these two PDFs and cite the differences", PRODUCTIVITY_TOOLS
    )

    assert profile == "library"
    assert {"find", "document_read", "document_query", "document_compare", "final"} <= _names(tools)
    assert "delete" not in _names(tools)


def test_ordinary_request_uses_direct_profile_without_unrelated_native_tools() -> None:
    tools, profile = DeepSpaceChatService._productivity_tools_for_prompt(
        "Help me solve this difficult problem", PRODUCTIVITY_TOOLS
    )

    assert profile == "direct"
    assert _names(tools) == {"ask_user"}


def test_is_placeholder_response_identifies_stalling_messages() -> None:
    assert (
        DeepSpaceChatService._is_placeholder_response(
            "I am searching for the latest news regarding general announcements... Please wait while I compile this information for you."
        )
        is True
    )
    assert DeepSpaceChatService._is_placeholder_response("Please wait while I look this up") is True
    assert (
        DeepSpaceChatService._is_placeholder_response(
            "Here are the latest announcements from OpenAI and Google..."
        )
        is False
    )


def test_explicit_agent_request_keeps_full_native_tool_set() -> None:
    tools, profile = DeepSpaceChatService._productivity_tools_for_prompt(
        "Plan and execute this multi-step workspace task", PRODUCTIVITY_TOOLS
    )

    assert profile == "full"
    assert tools == PRODUCTIVITY_TOOLS


def test_rolling_history_keeps_recent_turns_and_bounded_reference_digest() -> None:
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
