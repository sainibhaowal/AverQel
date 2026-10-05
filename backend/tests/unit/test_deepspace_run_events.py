from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm.exc import DetachedInstanceError

from app.deepspace.models.conversation import Conversation
from app.deepspace.services.run_events import (
    append_event,
    decode_live_event,
    event_name_from_frame,
    frames_after,
    is_terminal_event,
    latest_sequence,
    load_events,
    timeline_events,
)
from app.platform.database.session import managed_db_session
from app.realtime.event_bus import decode_event, stream_key
from app.system.models.user_notification import UserNotification


def test_realtime_event_envelope_is_bounded_and_tenant_scoped() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    assert stream_key(tenant_id, user_id) == f"averqel:realtime:v1:{tenant_id}:{user_id}"
    assert decode_event(
        {"payload": '{"type":"conversation.updated","resource":"conversations"}'}
    ) == {
        "type": "conversation.updated",
        "resource": "conversations",
    }
    assert decode_event({"payload": "not-json"}) is None


def test_event_name_is_read_from_real_sse_frame() -> None:
    assert event_name_from_frame("event: tool_result\ndata: {}\n\n") == "tool_result"


def test_live_event_payload_preserves_sequence_and_frame() -> None:
    assert decode_live_event(
        '{"sequence":7,"frame":"event: delta\\ndata: {\\"text\\":\\"hi\\"}\\n\\n"}'
    ) == (7, 'event: delta\ndata: {"text":"hi"}\n\n')
    assert decode_live_event("not-json") is None


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


def test_timeline_events_preserve_model_messages_between_tool_steps() -> None:
    events = [
        SimpleNamespace(
            sequence=1,
            event_name="model_message",
            created_at=datetime(2026, 8, 9, 10, 0, tzinfo=UTC),
            frame='event: model_message\ndata: {"text":"I am waiting for search results."}\n\n',
        ),
        SimpleNamespace(
            sequence=2,
            event_name="tool_start",
            created_at=datetime(2026, 8, 9, 10, 0, 1, tzinfo=UTC),
            frame='event: tool_start\ndata: {"tool_name":"web_search"}\n\n',
        ),
    ]

    replay = timeline_events(events)

    assert [item["event"] for item in replay] == ["model_message", "tool_start"]
    assert replay[0]["data"]["text"] == "I am waiting for search results."


def test_frames_after_filters_replayed_cursor() -> None:
    events = [
        SimpleNamespace(sequence=1, frame="one"),
        SimpleNamespace(sequence=3, frame="three"),
    ]

    assert frames_after(events, after_sequence=1) == [(3, "three")]


def test_replay_frames_survive_managed_session_close(db_session, settings, seed_user) -> None:
    """Regression: the DeepSpace SSE iterator must materialize replay frames
    while the ORM session is still open.

    Previously ``frames_after(stored, ...)`` ran *after*
    ``managed_db_session()`` had rolled back and closed the session. The
    rollback expires every loaded attribute, so touching ``event.sequence`` /
    ``event.frame`` on the detached rows raised ``DetachedInstanceError``.
    That unhandled exception aborted the streaming response without a terminal
    SSE event, which the UI reports as "The chat provider returned an empty
    stream." (STREAM_INCOMPLETE).
    """
    seeded = seed_user("replay-tenant", "replay@example.com", "StrongPass!1234", ("user",))
    tenant_id = seeded.tenant_id
    user_id = seeded.user_id
    conversation_id = uuid4()
    client_request_id = f"regression-replay-{uuid4()}"
    start_frame = "event: start\ndata: {}\n\n"
    delta_frame = 'event: delta\ndata: {"text":"hello"}\n\n'
    db_session.add(
        Conversation(
            id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title="Replay test",
            kind="deepspace",
        )
    )
    db_session.commit()

    append_event(
        db_session,
        settings=settings,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        frame=start_frame,
    )
    append_event(
        db_session,
        settings=settings,
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        frame=delta_frame,
    )

    stored = None
    with managed_db_session() as replay_db:
        stored = load_events(
            replay_db,
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
        )
        # Materialized inside the open session, exactly like the SSE iterator.
        replay_frames = frames_after(stored, after_sequence=0)

    # The managed session is now closed. Plain tuples must remain fully usable.
    assert replay_frames == [(1, start_frame), (2, delta_frame)]
    assert [frame for _, frame in replay_frames] == [start_frame, delta_frame]

    # Guard: reading ORM attributes after the session close reproduces the
    # original crash, proving this test exercises real detached ORM rows
    # rather than SimpleNamespace mocks.
    with pytest.raises(DetachedInstanceError):
        _ = stored[0].sequence  # type: ignore[index]


def test_latest_sequence_is_an_authorized_resume_cursor(db_session, settings, seed_user) -> None:
    seeded = seed_user("cursor-tenant", "cursor@example.com", "StrongPass!1234", ("user",))
    conversation_id = uuid4()
    request_id = f"resume-cursor-{uuid4()}"
    db_session.add(
        Conversation(
            id=conversation_id,
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            title="Resume cursor test",
            kind="deepspace",
        )
    )
    db_session.commit()
    for frame in ("event: start\ndata: {}\n\n", "event: done\ndata: {}\n\n"):
        append_event(
            db_session,
            settings=settings,
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
            client_request_id=request_id,
            frame=frame,
        )

    assert (
        latest_sequence(
            db_session,
            tenant_id=seeded.tenant_id,
            user_id=seeded.user_id,
            conversation_id=conversation_id,
            client_request_id=request_id,
        )
        == 2
    )
    run_notification = (
        db_session.query(UserNotification)
        .filter_by(recipient_user_id=seeded.user_id, event_type="run_completed")
        .one()
    )
    assert run_notification.href == f"/dashboard/deepspace?conversation={conversation_id}"


def test_timeline_coalesces_adjacent_thinking_but_not_across_tools() -> None:
    events = [
        SimpleNamespace(
            sequence=1,
            event_name="thinking",
            created_at=datetime.now(UTC),
            frame='event: thinking\ndata: {"text":"a"}\n\n',
        ),
        SimpleNamespace(
            sequence=2,
            event_name="thinking",
            created_at=datetime.now(UTC),
            frame='event: thinking\ndata: {"text":"b"}\n\n',
        ),
        SimpleNamespace(
            sequence=3,
            event_name="agent_testing",
            created_at=datetime.now(UTC),
            frame='event: agent_testing\ndata: {"message":"test"}\n\n',
        ),
        SimpleNamespace(
            sequence=4,
            event_name="thinking",
            created_at=datetime.now(UTC),
            frame='event: thinking\ndata: {"text":"c"}\n\n',
        ),
    ]

    replay = timeline_events(events)

    assert [item["event"] for item in replay] == [
        "thinking",
        "agent_testing",
        "thinking",
    ]
    assert replay[0]["data"]["text"] == "ab"
    assert replay[0]["sequence_end"] == 2
