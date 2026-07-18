from __future__ import annotations

from typing import Any

from app.services.deepspace.runtime.runtime_events import RuntimeEvent
from app.services.query.answer_service import AnswerService, StreamEvent


class DeepSpaceSseEventMapper:
    """Maps runtime and orchestration events onto the stable DeepSpace SSE contract."""

    @staticmethod
    def stream_event(event: str, data: dict[str, Any] | None = None) -> StreamEvent:
        payload = dict(data or {})
        raw_sequence = payload.get("sequence")
        sequence = raw_sequence if isinstance(raw_sequence, int) and raw_sequence >= 0 else None
        return StreamEvent(event=event, data=payload, sequence=sequence)

    @classmethod
    def encode(cls, event: str, data: dict[str, Any] | None = None) -> str:
        return AnswerService.encode_sse_event(cls.stream_event(event, data))

    @classmethod
    def encode_stream_event(cls, event: StreamEvent) -> str:
        return AnswerService.encode_sse_event(event)

    @classmethod
    def from_runtime_event(cls, event: RuntimeEvent) -> StreamEvent:
        return cls.stream_event(event.name, event.data)

    @classmethod
    def map_agent_step_event(
        cls,
        *,
        step_type: str,
        payload: dict[str, Any],
        agent_steps_count: int | None = None,
    ) -> list[StreamEvent]:
        if step_type == "agent_plan":
            return [cls.stream_event("agent_plan", payload)]
        if step_type == "tool_start":
            return [cls.stream_event("tool_start", payload)]
        if step_type == "tool_result":
            return [cls.stream_event("tool_result", payload)]
        if step_type == "observing":
            return [cls.stream_event("observing", payload)]
        if step_type == "tool_delta":
            return [cls.stream_event("tool_delta", payload)]
        if step_type == "tool_error":
            return [cls.stream_event("tool_error", payload)]
        if step_type == "permission_request":
            return [cls.stream_event("permission_request", payload)]
        if step_type == "ask_user_question":
            return [cls.stream_event("ask_user_question", payload)]
        if step_type == "agent_thinking":
            return [cls.stream_event("thinking", payload)]
        if step_type == "agent_testing":
            return [cls.stream_event("agent_testing", payload)]
        if step_type == "agent_verifying":
            return [cls.stream_event("agent_verifying", payload)]
        if step_type == "agent_self_correct":
            return [cls.stream_event("agent_self_correct", payload)]
        if step_type == "step_start":
            return [cls.stream_event("step_start", payload)]
        if step_type == "step_finish":
            return [cls.stream_event("step_finish", payload)]
        if step_type == "answer_delta":
            return [cls.stream_event("delta", payload)]
        if step_type == "answer_done":
            # The service emits the terminal `done` only after the assistant
            # message has been committed. Sending it here makes the browser
            # close the WebSocket before persistence completes.
            return []
        if step_type == "final_answer":
            text = str(payload.get("content") or "")
            return [cls.stream_event("delta", {"text": text})]
        if step_type == "step_summary":
            return [cls.stream_event("step_summary", payload)]
        return []

    @classmethod
    def map_orchestrator_event(
        cls,
        *,
        event_name: str,
        payload: dict[str, Any],
        is_main_lane: bool,
        mission_summary: str | None = None,
    ) -> list[StreamEvent]:
        if event_name == "mission_start":
            return [
                cls.stream_event("mission_start", payload),
                cls.stream_event(
                    "agent_status",
                    {
                        "mission_id": payload.get("mission_id"),
                        "status": "running",
                        "message": "Unified orchestration mission started.",
                        "execution_mode": payload.get("execution_mode"),
                    },
                ),
            ]
        if event_name == "mission_planning":
            return [
                cls.stream_event("mission_planning", payload),
                cls.stream_event("agent_status", payload),
            ]
        if event_name == "mission_plan":
            return [cls.stream_event("mission_plan", payload)]
        if event_name == "mission_graph":
            return [cls.stream_event("mission_graph", payload)]
        if event_name == "mission_summary":
            return [
                cls.stream_event("mission_summary", payload),
                cls.stream_event(
                    "agent_status",
                    {"summary": str(payload.get("summary") or mission_summary or "")},
                ),
            ]
        if event_name == "mission_done":
            return [cls.stream_event("mission_done", payload)]
        if event_name == "approval_request":
            events = [cls.stream_event("approval_request", payload)]
            if is_main_lane:
                events.append(cls.stream_event("permission_request", payload))
            else:
                events.append(
                    cls.stream_event("agent_status", {**payload, "event": event_name})
                )
            return events

        if event_name == "lane_tool_delta" and is_main_lane:
            return [cls.stream_event("tool_delta", payload)]
        if event_name == "lane_start":
            events = [cls.stream_event("lane_start", payload)]
            return events
        if event_name in {
            "lane_delta",
            "lane_thinking",
            "lane_agent_thinking",
            "lane_result",
            "lane_error",
            "lane_step_summary",
            "lane_observation",
            "lane_blocked",
        }:
            events = [cls.stream_event(event_name, payload)]
            if is_main_lane:
                legacy_map = {
                    "lane_delta": "delta",
                    "lane_thinking": "thinking",
                    "lane_agent_thinking": "thinking",
                    "lane_result": "agent_status",
                    "lane_error": "tool_error",
                    "lane_step_summary": "step_summary",
                    "lane_observation": "observing",
                    "lane_blocked": "agent_status",
                }
                mapped = legacy_map.get(event_name)
                if mapped == "delta":
                    events.append(
                        cls.stream_event(
                            mapped, {"text": str(payload.get("text") or ""), **payload}
                        )
                    )
                elif mapped == "thinking":
                    events.append(cls.stream_event(mapped, payload))
                elif mapped == "observing":
                    events.append(cls.stream_event(mapped, payload))
                elif mapped == "step_summary":
                    events.append(cls.stream_event(mapped, payload))
                elif mapped == "tool_error":
                    events.append(cls.stream_event(mapped, payload))
                elif mapped == "agent_status":
                    events.append(
                        cls.stream_event(mapped, {**payload, "event": event_name})
                    )
            return events

        if event_name == "lane_tool_start" and is_main_lane:
            return [
                cls.stream_event("tool_start", payload),
            ]
        if event_name == "lane_tool_result" and is_main_lane:
            return [
                cls.stream_event("tool_result", payload),
            ]

        return [cls.stream_event("agent_status", {**payload, "event": event_name})]
