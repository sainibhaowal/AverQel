from app.services.deepspace.runtime.sse_event_mapper import DeepSpaceSseEventMapper
from app.services.query.answer_service import AnswerService


def test_sse_mapper_preserves_orchestration_event_contract_for_non_main_lane():
    events = DeepSpaceSseEventMapper.map_orchestrator_event(
        event_name="lane_result",
        payload={
            "mission_id": "mission-1",
            "lane_id": "research_lane",
            "lane_type": "research",
            "status": "completed",
            "summary": "Research finished.",
        },
        is_main_lane=False,
        mission_summary=None,
    )

    assert [event.event for event in events] == ["lane_result"]
    assert events[0].data["lane_id"] == "research_lane"


def test_sse_mapper_keeps_main_lane_legacy_delta_and_lane_delta():
    events = DeepSpaceSseEventMapper.map_orchestrator_event(
        event_name="lane_delta",
        payload={
            "mission_id": "mission-1",
            "lane_id": "main_chat",
            "lane_type": "main_chat",
            "text": "Hello",
        },
        is_main_lane=True,
        mission_summary=None,
    )

    assert [event.event for event in events] == ["lane_delta", "delta"]
    assert events[1].data["text"] == "Hello"


def test_sequence_is_encoded_as_sse_id_without_changing_event_name():
    event = DeepSpaceSseEventMapper.stream_event(
        "runtime_event",
        {"sequence": 17, "run_id": "run-1", "status": "running"},
    )

    encoded = AnswerService.encode_sse_event(event)

    assert event.sequence == 17
    assert encoded.startswith("id: 17\nevent: runtime_event\n")
    assert '"sequence":17' in encoded
