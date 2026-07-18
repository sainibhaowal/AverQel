from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.deepspace.subagents.subagent_profiles import SubagentProfile


@dataclass(slots=True)
class SubagentResultAccumulator:
    final_answer: str = ""
    streamed_answer: list[str] = field(default_factory=list)
    step_summaries: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    agent_messages: list[str] = field(default_factory=list)

    def record_event(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "final_answer":
            content = data.get("content") or data.get("message")
            if isinstance(content, str) and content.strip():
                self.final_answer = content.strip()
        elif event_type == "answer_delta":
            text = data.get("text")
            if isinstance(text, str) and text.strip():
                self.streamed_answer.append(text)
        elif event_type == "step_summary":
            message = data.get("message")
            if isinstance(message, str) and message.strip():
                self.step_summaries.append(message.strip())
        elif event_type == "agent_response":
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                self.agent_messages.append(content.strip())
        elif event_type == "observing":
            summary = data.get("summary") or data.get("message")
            if isinstance(summary, str) and summary.strip():
                self.observations.append(summary.strip())

    def best_output(self) -> str:
        if self.final_answer:
            return self.final_answer
        streamed = "".join(self.streamed_answer).strip()
        if streamed:
            return streamed
        for collection in (
            self.agent_messages,
            self.step_summaries,
            self.observations,
        ):
            for item in reversed(collection):
                if item.strip():
                    return item.strip()
        return ""


def normalize_subagent_result(
    *,
    profile: SubagentProfile,
    accumulator: SubagentResultAccumulator,
    prompt: str,
    sub_conversation_id: uuid.UUID,
    run_id: str,
    parent_id: uuid.UUID,
) -> tuple[str, dict[str, Any]]:
    output = accumulator.best_output().strip()
    if not output:
        output = (
            f"No explicit {profile.canonical_type} result was produced for: "
            f"{str(prompt or '').strip()}"
        )

    normalized_output = (
        f"SUB-AGENT MISSION COMPLETE [{profile.canonical_type.upper()}]:\n\n{output}"
    )
    metadata = {
        "subagent_type": profile.canonical_type,
        "requested_subagent_type": profile.requested_type,
        "subagent_display_name": profile.display_name,
        "sub_id": str(sub_conversation_id),
        "subagent_run_id": run_id,
        "parent_id": str(parent_id),
    }
    return normalized_output, metadata
