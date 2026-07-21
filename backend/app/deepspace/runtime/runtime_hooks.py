from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.deepspace.runtime.runtime_context import RuntimeContext, ToolRuntimeContext

logger = logging.getLogger(__name__)
_MAX_RECENT_HOOK_EVENTS = 24

Payload = dict[str, Any]
TransformHook = Callable[
    [RuntimeContext, Payload], Payload | None | Awaitable[Payload | None]
]
ToolTransformHook = Callable[
    [ToolRuntimeContext, Payload], Payload | None | Awaitable[Payload | None]
]
ObserveHook = Callable[[RuntimeContext, Payload], Any | Awaitable[Any]]
ToolObserveHook = Callable[[ToolRuntimeContext, Payload], Any | Awaitable[Any]]


@dataclass(slots=True)
class RuntimeHooks:
    """Lifecycle hook registry for the DeepSpace runtime."""

    pre_turn: list[TransformHook] = field(default_factory=list)
    post_turn: list[ObserveHook] = field(default_factory=list)
    pre_tool: list[ToolTransformHook] = field(default_factory=list)
    post_tool: list[ToolObserveHook] = field(default_factory=list)
    on_tool_error: list[ToolObserveHook] = field(default_factory=list)
    pre_answer_finalize: list[TransformHook] = field(default_factory=list)

    async def run_pre_turn(self, context: RuntimeContext, payload: Payload) -> Payload:
        return await _run_transform_hooks(self.pre_turn, context, payload)

    async def run_post_turn(self, context: RuntimeContext, payload: Payload) -> None:
        await _run_observe_hooks(self.post_turn, context, payload)

    async def run_pre_tool(
        self, context: ToolRuntimeContext, payload: Payload
    ) -> Payload:
        return await _run_transform_hooks(self.pre_tool, context, payload)

    async def run_post_tool(
        self, context: ToolRuntimeContext, payload: Payload
    ) -> None:
        await _run_observe_hooks(self.post_tool, context, payload)

    async def run_tool_error(
        self, context: ToolRuntimeContext, payload: Payload
    ) -> None:
        await _run_observe_hooks(self.on_tool_error, context, payload)

    async def run_pre_answer_finalize(
        self, context: RuntimeContext, payload: Payload
    ) -> Payload:
        return await _run_transform_hooks(self.pre_answer_finalize, context, payload)


def summarize_runtime_hooks_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("hook_diagnostics")
    if not isinstance(raw, dict):
        return {
            "active": False,
            "counts": {},
            "recent": [],
        }
    counts_value = raw.get("counts")
    recent_value = raw.get("recent")
    counts: dict[str, Any] = counts_value if isinstance(counts_value, dict) else {}
    recent: list[Any] = recent_value if isinstance(recent_value, list) else []
    return {
        "active": bool(sum(int(value or 0) for value in counts.values())),
        "counts": {
            str(key): int(value or 0)
            for key, value in counts.items()
            if str(key).strip()
        },
        "recent": [item for item in recent if isinstance(item, dict)][
            -_MAX_RECENT_HOOK_EVENTS:
        ],
    }


async def _run_transform_hooks(
    hooks: list[Callable[..., Any]],
    context: RuntimeContext,
    payload: Payload,
) -> Payload:
    current = dict(payload)
    for hook in hooks:
        hook_name = _hook_name(hook)
        try:
            before = dict(current)
            result = hook(context, dict(current))
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict):
                current.update(result)
            _record_hook_event(
                context,
                phase=str(getattr(context, "phase", "") or "runtime"),
                hook_name=hook_name,
                changed_fields=_changed_fields(before, current),
                status="applied",
            )
        except Exception:  # noqa: BLE001
            _record_hook_event(
                context,
                phase=str(getattr(context, "phase", "") or "runtime"),
                hook_name=hook_name,
                changed_fields=[],
                status="error",
            )
            logger.debug("Runtime transform hook failed.", exc_info=True)
    return current


async def _run_observe_hooks(
    hooks: list[Callable[..., Any]],
    context: RuntimeContext,
    payload: Payload,
) -> None:
    for hook in hooks:
        hook_name = _hook_name(hook)
        try:
            result = hook(context, dict(payload))
            if inspect.isawaitable(result):
                await result
            _record_hook_event(
                context,
                phase=str(getattr(context, "phase", "") or "runtime"),
                hook_name=hook_name,
                changed_fields=[],
                status="observed",
            )
        except Exception:  # noqa: BLE001
            _record_hook_event(
                context,
                phase=str(getattr(context, "phase", "") or "runtime"),
                hook_name=hook_name,
                changed_fields=[],
                status="error",
            )
            logger.debug("Runtime observe hook failed.", exc_info=True)


def _hook_name(hook: Callable[..., Any]) -> str:
    return getattr(hook, "__name__", hook.__class__.__name__) or "anonymous_hook"


def _changed_fields(before: Payload, after: Payload) -> list[str]:
    changed = {
        str(key)
        for key in set(before.keys()) | set(after.keys())
        if before.get(key) != after.get(key)
    }
    return sorted(item for item in changed if item)


def _record_hook_event(
    context: RuntimeContext,
    *,
    phase: str,
    hook_name: str,
    changed_fields: list[str],
    status: str,
) -> None:
    diagnostics = context.state.setdefault("hook_diagnostics", {})
    if not isinstance(diagnostics, dict):
        return
    counts = diagnostics.setdefault("counts", {})
    recent = diagnostics.setdefault("recent", [])
    if isinstance(counts, dict):
        counts[phase] = int(counts.get(phase) or 0) + 1
    event = {
        "phase": phase,
        "hook": hook_name,
        "status": status,
        "changed_fields": list(changed_fields),
        "tool_name": getattr(context, "tool_name", None),
        "step_id": getattr(context, "step_id", None),
        "turn_index": getattr(context, "turn_index", None),
    }
    if isinstance(recent, list):
        recent.append(event)
        del recent[:-_MAX_RECENT_HOOK_EVENTS]
