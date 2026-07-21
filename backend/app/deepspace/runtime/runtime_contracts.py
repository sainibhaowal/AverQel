from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return len(_serialize_messages(messages)) // 4


def _serialize_messages(messages: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{str(message.get('role') or '').strip()}:{str(message.get('content') or '').strip()}"
        for message in messages
        if str(message.get("content") or "").strip()
    )


def normalize_message_snapshot(
    value: Any,
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower() or "system"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


@dataclass(slots=True)
class ConversationCompactionState:
    version: int
    trigger: str
    compacted_at: str
    anchor_message_id: str | None
    summary: str
    summarized_count: int
    kept_recent_count: int
    before_tokens: int
    after_tokens: int
    saved_tokens: int
    compacted_messages: list[dict[str, str]]

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


def build_conversation_compaction_state(
    *,
    base_messages: list[dict[str, Any]],
    trigger: str,
    anchor_message_id: str | None,
    keep_recent_messages: int = 8,
) -> ConversationCompactionState | None:
    normalized_messages = normalize_message_snapshot(base_messages)
    if len(normalized_messages) <= max(keep_recent_messages + 1, 2):
        return None

    recent_count = max(4, keep_recent_messages)
    head = normalized_messages[:1]
    middle = normalized_messages[1:-recent_count]
    recent = normalized_messages[-recent_count:]
    if not middle:
        return None

    summary_lines: list[str] = []
    for item in middle:
        role = "User" if item["role"] == "user" else "Assistant"
        text = item["content"].replace("\n", " ").strip()
        if len(text) > 180:
            text = f"{text[:177].rstrip()}..."
        summary_lines.append(f"- {role}: {text}")

    summary = "Compacted conversation history:\n" + "\n".join(summary_lines[:18])
    compacted_messages = [
        *head,
        {"role": "system", "content": summary},
        *recent,
    ]
    before_tokens = estimate_messages_tokens(normalized_messages)
    after_tokens = estimate_messages_tokens(compacted_messages)
    return ConversationCompactionState(
        version=1,
        trigger=str(trigger or "manual"),
        compacted_at=_now_iso(),
        anchor_message_id=anchor_message_id,
        summary=summary,
        summarized_count=len(middle),
        kept_recent_count=len(recent),
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        saved_tokens=max(before_tokens - after_tokens, 0),
        compacted_messages=compacted_messages,
    )


def normalize_conversation_compaction_state(
    value: Any,
) -> ConversationCompactionState | None:
    if not isinstance(value, dict):
        return None
    compacted_messages = normalize_message_snapshot(value.get("compacted_messages"))
    compacted_at = str(value.get("compacted_at") or "").strip() or _now_iso()
    trigger = str(value.get("trigger") or "manual").strip() or "manual"
    anchor_message_id = value.get("anchor_message_id")
    anchor = str(anchor_message_id).strip() if anchor_message_id else None
    summary = str(value.get("summary") or "").strip()
    before_tokens = int(value.get("before_tokens") or 0)
    after_tokens = int(value.get("after_tokens") or 0)
    state = ConversationCompactionState(
        version=int(value.get("version") or 1),
        trigger=trigger,
        compacted_at=compacted_at,
        anchor_message_id=anchor,
        summary=summary,
        summarized_count=int(value.get("summarized_count") or 0),
        kept_recent_count=int(
            value.get("kept_recent_count") or len(compacted_messages)
        ),
        before_tokens=max(before_tokens, 0),
        after_tokens=max(after_tokens, 0),
        saved_tokens=max(
            int(value.get("saved_tokens") or (before_tokens - after_tokens)), 0
        ),
        compacted_messages=compacted_messages,
    )
    if not state.compacted_messages:
        return None
    return state


def resolve_compacted_session_messages(
    *,
    history_messages: list[dict[str, Any]],
    compaction_state: ConversationCompactionState | None,
) -> list[dict[str, str]]:
    normalized_history = normalize_message_snapshot(history_messages)
    if compaction_state is None:
        return normalized_history
    compacted = list(compaction_state.compacted_messages)
    if not compaction_state.anchor_message_id:
        return compacted

    tail_start = None
    for idx, item in enumerate(history_messages):
        message_id = str(item.get("message_id") or item.get("id") or "").strip()
        if message_id == compaction_state.anchor_message_id:
            tail_start = idx + 1
            break
    if tail_start is None:
        return compacted
    return compacted + normalize_message_snapshot(history_messages[tail_start:])
