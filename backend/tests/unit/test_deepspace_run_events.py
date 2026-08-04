from app.deepspace.services.run_events import (
    decode_live_event,
    event_name_from_frame,
    is_terminal_event,
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
