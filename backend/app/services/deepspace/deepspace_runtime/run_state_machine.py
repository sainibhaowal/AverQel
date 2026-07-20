from __future__ import annotations

RUN_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"paused", "awaiting_approval", "recovering", "completed", "failed", "cancelled"},
    "paused": {"queued", "running", "cancelled", "failed"},
    "awaiting_approval": {"queued", "running", "cancelled", "failed"},
    "recovering": {"queued", "running", "failed", "cancelled"},
    "completed": set(),
    "failed": {"queued", "recovering"},
    "cancelled": set(),
}

NODE_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"ready", "blocked", "cancelled"},
    "ready": {"running", "blocked", "cancelled"},
    "running": {"awaiting_approval", "completed", "failed", "retrying", "cancelled"},
    "retrying": {"ready", "failed", "cancelled"},
    "awaiting_approval": {"ready", "cancelled", "failed"},
    "blocked": {"ready", "cancelled"},
    "completed": set(),
    "failed": {"retrying", "cancelled"},
    "cancelled": set(),
}


class InvalidRunTransitionError(ValueError):
    pass


def ensure_transition(*, current: str, target: str, node: bool = False) -> None:
    transitions = NODE_TRANSITIONS if node else RUN_TRANSITIONS
    current = str(current or "").lower()
    target = str(target or "").lower()
    if current == target:
        return
    if target not in transitions.get(current, set()):
        scope = "node" if node else "run"
        raise InvalidRunTransitionError(f"invalid durable {scope} transition: {current} -> {target}")
