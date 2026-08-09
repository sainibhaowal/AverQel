from datetime import UTC, datetime
from types import SimpleNamespace

from app.deepspace.services.run_events import (
    decode_live_event,
    event_name_from_frame,
    is_terminal_event,
    timeline_events,
)


def test_event_name_is_read_from_real_sse_frame() -> None:
    assert event_name_from_frame("event: tool_result\ndata: {}\n\n") == "tool_result"


def test_live_event_payload_preserves_sequence_and_frame() -> None:
    assert decode_live_event(
        '{"sequence":7,"frame":"event: delta\\ndata: {\\"text\\":\\"hi\\"}\\n\\n"}'
    ) == (7, 'event: delta\ndata: {"text":"hi"}\n\n')


def test_only_done_and_error_close_a_detached_stream() -> None:
    assert is_terminal_event("done")
    assert is_terminal_event("error")
    assert not is_terminal_event("delta")


def test_timeline_events_preserve_thinking_tool_thinking_order() -> None:
    events = [
        SimpleNamespace(
            sequence=1,
            event_name="thinking",
            created_at=datetime(2026, 8, 9, 10, 0, tzinfo=UTC),
            frame='event: thinking\ndata: {"text":"first thought"}\n\n',
        ),
        SimpleNamespace(
            sequence=2,
            event_name="tool_start",
            created_at=datetime(2026, 8, 9, 10, 0, 1, tzinfo=UTC),
            frame='event: tool_start\ndata: {"tool_name":"web_search","tool_id":"call-1"}\n\n',
        ),
        SimpleNamespace(
            sequence=3,
            event_name="tool_result",
            created_at=datetime(2026, 8, 9, 10, 0, 2, tzinfo=UTC),
            frame='event: tool_result\ndata: {"tool_name":"web_search","tool_id":"call-1","success":true}\n\n',
        ),
        SimpleNamespace(
            sequence=4,
            event_name="thinking",
            created_at=datetime(2026, 8, 9, 10, 0, 3, tzinfo=UTC),
            frame='event: thinking\ndata: {"text":"second thought"}\n\n',
        ),
    ]

    replay = timeline_events(events)

    assert [item["event"] for item in replay] == [
        "thinking",
        "tool_start",
        "tool_result",
        "thinking",
    ]
    assert replay[0]["data"]["text"] == "first thought"
    assert replay[3]["data"]["text"] == "second thought"
