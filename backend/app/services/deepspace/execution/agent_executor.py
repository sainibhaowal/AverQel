"""
Agent Executor: The Core Intelligence Loop for DeepSpace.

Implements the agentic reasoning loop:
  PLAN -> EXECUTE -> OBSERVE -> EVALUATE -> REPEAT or ANSWER

The executor calls the LLM with function-calling (tool use) enabled.
When the LLM decides to use a tool, the executor runs it, feeds the
result back, and lets the LLM decide the next step. This continues
until the LLM produces a final text answer or the step limit is reached.

Each step is emitted as an AgentStepEvent so the frontend can render
real-time collapsible panels showing the agent's internal process.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext
from app.core.brand import APP_ASSISTANT_NAME, APP_BRAND_NAME, APP_ENGINE_NAME
from app.core.config import Settings
from app.repositories.query.chat import ChatRepository
from app.services.deepspace.autonomy import AutonomyController, GoalContract
from app.services.deepspace.execution.adaptive_supervisor import AdaptiveExecutionSupervisor
from app.services.deepspace.execution.agent_tools import (
    ALL_TOOLS,
    TOOL_MAP,
    ToolExecutor,
)
from app.services.deepspace.execution.reliability import CircuitBreaker
from app.services.deepspace.execution.tool_context import ToolContext
from app.services.deepspace.missions.mission_registry import MissionRegistry
from app.services.deepspace.deepspace_runtime.runtime_context import RuntimeContext, ToolRuntimeContext
from app.services.deepspace.deepspace_runtime.runtime_contracts import (
    build_conversation_compaction_state,
    estimate_messages_tokens,
)
from app.services.deepspace.deepspace_runtime.runtime_hooks import (
    RuntimeHooks,
    summarize_runtime_hooks_state,
)
from app.services.deepspace.deepspace_runtime.runtime_policy import (
    RuntimePolicy,
    summarize_runtime_policy_state,
)
from app.services.deepspace.workspace.coding_harness import CodingHarness, CodingMissionContract
from app.services.deepspace.workspace.workspace_mode import WorkspaceMode
from app.services.deepspace.workspace.workspace_policy import WorkspacePolicy
from app.providers.services.base import ProviderRequestError
from app.providers.services.reasoning_capabilities import reasoning_capabilities
from app.providers.services.registry import ProviderRegistry
from app.providers.services.selection_service import ProviderSelectionService
from app.providers.services.types import ChatGenerateRequest
from app.system.services.otel import trace_async, trace_async_generator

logger = logging.getLogger(__name__)

UTC = getattr(datetime, "UTC", UTC)

TEXTUAL_TOOL_NAME_MAP = {
    "ASK_USER_QUESTION": "ask_user_question",
    "TODO_WRITE": "todo_write",
    "ENTER_PLAN_MODE": "enter_plan_mode",
    "MEMORY_WRITE": "memory_write",
}


@dataclass(slots=True)
class AgentStepEvent:
    """
    A single event emitted during the agent loop.
    The frontend renders each event as a step in the agent panel.
    """

    type: str  # agent_plan | tool_start | tool_delta | tool_result | tool_error
    # | permission_request | answer_start | answer_delta | answer_done | agent_thinking
    # | observing | step_summary | agent_testing | agent_verifying | agent_self_correct
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallRequest:
    """Parsed tool call from the LLM response."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class _RuntimeCacheEntry:
    resolved_at: float
    provider_type: str | None
    model_name: str | None
    base_url: str | None
    api_key: str | None
    resolved_context_limit: int | None
    reported_context_limit: int | None
    context_limit_source: str
    used_default_provider: bool = False


@dataclass(slots=True)
class _MemoryBootstrapCacheEntry:
    cached_at: float
    facts: list[dict[str, Any]]


class AgentExecutor:
    """
    The Golden Agent Loop.

    Calls the LLM with tool definitions. If the LLM returns tool_calls,
    executes them and feeds results back. If it returns text, streams it
    as the final answer.
    """

    # Kept as a compatibility alias only.  Execution is governed by the
    # adaptive supervisor and mission budgets, not by a fixed 12-turn loop.
    MAX_STEPS = None
    AUTO_COMPACTION_THRESHOLD = 0.82
    STREAM_IDLE_TIMEOUT_MULTIPLIER = 4.0
    RUNTIME_CACHE_TTL_SECONDS = 15.0
    MEMORY_BOOTSTRAP_CACHE_TTL_SECONDS = 10.0
    _runtime_cache: dict[tuple[str, str], _RuntimeCacheEntry] = {}
    _runtime_cache_lock = threading.Lock()
    _memory_bootstrap_cache: dict[
        tuple[str, str, str, int], _MemoryBootstrapCacheEntry
    ] = {}
    _memory_bootstrap_cache_lock = threading.Lock()
    SYSTEM_INSTRUCTION = (
        f"You are {APP_ASSISTANT_NAME}, the {APP_BRAND_NAME} intelligence running on the {APP_ENGINE_NAME} engine.\n\n"
        "TRUE AUTONOMY:\n"
        "- You have complete autonomy to decide your approach for each user request.\n"
        "- Decide for yourself: Should I answer directly from context, or use tools, or create a plan, or use todo lists?\n"
        "- Decide for yourself: Should I continue with more steps, or is the current answer sufficient?\n"
        "- Decide for yourself: What tools (if any) are needed, and in what order?\n"
        "- There are NO predefined rituals, NO keyword triggers, NO fixed phases. You drive the entire process.\n\n"
        "EXECUTION STRATEGY:\n"
        "- For simple questions: Answer directly from context without tools.\n"
        "- For complex tasks: Use tools as needed, create plans if helpful, manage todo lists for tracking.\n"
        "- Stop when you have a satisfactory answer. Do not continue unnecessarily.\n"
        "- If you use tools, ensure the results inform your final answer.\n\n"
        "PERMISSIONS:\n"
        "- Respect the 5-Tier system; destructive or gated tools require approval as enforced by the runtime.\n\n"
        "WORKSPACE VALIDATION:\n"
        "- Never assume files exist or contain specific content. If you need to edit or reference code, use filesystem tools to verify.\n"
    )

    @staticmethod
    def _detect_phase(
        tool_name: str, args: dict[str, Any] | None, last_phase: str
    ) -> str:
        """Deprecated: Phase tracking removed for true LLM autonomy."""
        # The LLM now decides its own approach; phases are not enforced
        return "autonomous"

    def __init__(
        self,
        db: Session,
        auth: AuthContext,
        settings: Settings | None = None,
        background_tasks: Any | None = None,
        restricted_tools: list[str] | None = None,
        run_control: Any | None = None,
        execution_mode: str = "auto_review",
        runtime_hooks: RuntimeHooks | None = None,
        runtime_policy: RuntimePolicy | None = None,
        mission_id: str | None = None,
        mission_registry: MissionRegistry | None = None,
    ) -> None:
        self.db = db
        self.auth = auth
        from app.core.config import get_settings

        self.settings = settings or get_settings()
        self.background_tasks = background_tasks
        self.restricted_tools = restricted_tools
        self.run_control = run_control
        self.mission_id = mission_id
        self.mission_registry = mission_registry
        self.execution_mode = (
            "full_access"
            if str(execution_mode).strip().lower() == "full_access"
            else "auto_review"
        )
        self.tool_executor = ToolExecutor(db=db, settings=self.settings, auth=auth)
        self.tool_executor.execution_mode = self.execution_mode
        self.runtime_hooks = runtime_hooks or RuntimeHooks()
        self.runtime_policy = runtime_policy or RuntimePolicy()
        self.workspace_policy = WorkspacePolicy()
        self.workspace_mode = WorkspaceMode()
        self.provider_selection = ProviderSelectionService(self.db, self.settings)
        self._resolved_llm = None
        self._resolved_model_name: str | None = None
        self._resolved_provider_type: str | None = None
        self._resolved_base_url: str | None = None
        self._resolved_api_key: str | None = None
        self._resolved_context_limit: int | None = None
        self._reported_context_limit: int | None = None
        self._resolved_context_limit_source: str = "unknown"
        self._last_compaction_state: dict[str, Any] | None = None
        self._runtime_state_store: dict[str, Any] = {}
        self._provider_circuit = CircuitBreaker()

    def _max_execution_steps(self) -> int | None:
        """Return an optional legacy override for the adaptive supervisor."""
        # Test/runtime doubles may not carry the Settings field; retain the
        # historical small fallback there while production Settings defaults
        # to the adaptive 256-turn supervisor ceiling.
        configured = getattr(self.settings, "deepspace_agent_max_steps", 12)
        return int(configured) if isinstance(configured, int) and configured > 0 else None

    def _resolve_runtime(self) -> Any:
        if self._resolved_llm is not None:
            return self._resolved_llm

        registry = ProviderRegistry(self.settings)
        cache_key = (str(self.auth.tenant_id), str(self.auth.user_id))
        cache_entry = self._get_cached_runtime(cache_key)
        if cache_entry is None:
            selection = self.provider_selection.resolve_chat(
                tenant_id=self.auth.tenant_id,
                actor_user_id=self.auth.user_id,
            )
            candidate = selection.candidates[0] if selection.candidates else None
            if candidate is None:
                cache_entry = _RuntimeCacheEntry(
                    resolved_at=time.monotonic(),
                    provider_type=None,
                    model_name=None,
                    base_url=self.settings.llm_api_base_url or None,
                    api_key=self.settings.llm_api_key,
                    resolved_context_limit=self.settings.max_context_chars,
                    reported_context_limit=None,
                    context_limit_source="unknown",
                    used_default_provider=True,
                )
            else:
                reported_context_limit = (
                    candidate.context_window
                    if isinstance(candidate.context_window, int)
                    else None
                )
                resolved_context_limit = reported_context_limit
                context_limit_source = "unknown"
                if resolved_context_limit is None or resolved_context_limit <= 0:
                    resolved_context_limit = self.settings.max_context_chars
                    reported_context_limit = None
                else:
                    context_limit_source = (
                        candidate.context_window_source
                        if isinstance(candidate.context_window_source, str)
                        and candidate.context_window_source.strip()
                        else "live_model"
                    )
                cache_entry = _RuntimeCacheEntry(
                    resolved_at=time.monotonic(),
                    provider_type=candidate.provider_type,
                    model_name=candidate.model_name or self.settings.llm_model or None,
                    base_url=candidate.base_url
                    or self.settings.llm_api_base_url
                    or None,
                    api_key=candidate.api_key or self.settings.llm_api_key,
                    resolved_context_limit=resolved_context_limit,
                    reported_context_limit=reported_context_limit,
                    context_limit_source=context_limit_source,
                    used_default_provider=False,
                )
            self._set_cached_runtime(cache_key, cache_entry)

        self._resolved_model_name = cache_entry.model_name
        self._resolved_provider_type = cache_entry.provider_type
        self._resolved_base_url = cache_entry.base_url
        self._resolved_api_key = cache_entry.api_key
        self._resolved_context_limit = cache_entry.resolved_context_limit
        self._reported_context_limit = cache_entry.reported_context_limit
        self._resolved_context_limit_source = cache_entry.context_limit_source
        if cache_entry.used_default_provider:
            self._resolved_llm = registry.get_chat_provider()
        else:
            self._resolved_llm = registry._bind_chat_provider(
                cache_entry.provider_type or self.settings.llm_provider,
                base_url=cache_entry.base_url,
                api_key=cache_entry.api_key,
            )
        return self._resolved_llm

    @classmethod
    def _get_cached_runtime(
        cls, cache_key: tuple[str, str]
    ) -> _RuntimeCacheEntry | None:
        now = time.monotonic()
        with cls._runtime_cache_lock:
            entry = cls._runtime_cache.get(cache_key)
            if entry is None:
                return None
            if (now - entry.resolved_at) > cls.RUNTIME_CACHE_TTL_SECONDS:
                cls._runtime_cache.pop(cache_key, None)
                return None
            return entry

    @classmethod
    def _set_cached_runtime(
        cls, cache_key: tuple[str, str], entry: _RuntimeCacheEntry
    ) -> None:
        with cls._runtime_cache_lock:
            cls._runtime_cache[cache_key] = entry

    @property
    def context_limit(self) -> int:
        self._resolve_runtime()
        return self._resolved_context_limit or self.settings.max_context_chars

    @property
    def reported_context_limit(self) -> int | None:
        self._resolve_runtime()
        return self._reported_context_limit

    @property
    def model_name(self) -> str | None:
        self._resolve_runtime()
        return self._resolved_model_name

    @property
    def provider_type(self) -> str | None:
        self._resolve_runtime()
        return self._resolved_provider_type

    @property
    def base_url(self) -> str | None:
        self._resolve_runtime()
        return self._resolved_base_url

    @property
    def api_key(self) -> str | None:
        self._resolve_runtime()
        return self._resolved_api_key

    @property
    def context_limit_source(self) -> str:
        self._resolve_runtime()
        return self._resolved_context_limit_source

    @staticmethod
    def _run_control_cancelled(run_control: Any | None) -> bool:
        checker = getattr(run_control, "is_cancelled", None)
        if not callable(checker):
            return False
        try:
            return bool(checker())
        except Exception:  # noqa: BLE001
            logger.debug("Run control cancellation check failed.", exc_info=True)
            return False

    @staticmethod
    def _run_control_touch(run_control: Any | None, **updates: Any) -> None:
        heartbeat = getattr(run_control, "heartbeat", None)
        if not callable(heartbeat):
            return
        try:
            heartbeat(**updates)
        except Exception:  # noqa: BLE001
            logger.debug("Run control heartbeat failed.", exc_info=True)

    @staticmethod
    def _build_observation_summary(tool_name: str, output: str, success: bool) -> str:
        normalized = " ".join(str(output or "").split())
        clipped = normalized[:400]
        prefix = "Observation from" if success else "Observation after failure from"
        return (
            f"{prefix} {tool_name}: {clipped}" if clipped else f"{prefix} {tool_name}."
        )

    def _reset_runtime_diagnostics(
        self,
        *,
        execution_mode: str,
        conversation_id: uuid.UUID | None,
    ) -> None:
        self._runtime_state_store = {
            "execution_mode": execution_mode,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "tool_metrics": {
                "started": 0,
                "completed": 0,
                "failed": 0,
                "blocked": 0,
                "awaiting_approval": 0,
            },
            "memory_markers": [],
            "compaction_markers": [],
        }

    def _record_memory_marker(
        self,
        *,
        kind: str,
        count: int,
        fast_bootstrap: bool,
    ) -> None:
        markers = self._runtime_state_store.setdefault("memory_markers", [])
        if not isinstance(markers, list):
            return
        markers.append(
            {
                "kind": kind,
                "count": max(int(count), 0),
                "fast_bootstrap": bool(fast_bootstrap),
            }
        )
        del markers[:-12]

    def _increment_tool_metric(self, key: str, amount: int = 1) -> None:
        metrics = self._runtime_state_store.setdefault("tool_metrics", {})
        if not isinstance(metrics, dict):
            return
        metrics[key] = int(metrics.get(key) or 0) + amount

    def _record_tool_result_metric(self, *, success: bool) -> None:
        self._increment_tool_metric("completed")
        if success:
            return
        self._increment_tool_metric("failed")

    def _record_compaction_marker(self, state: dict[str, Any] | None) -> None:
        if not isinstance(state, dict):
            return
        markers = self._runtime_state_store.setdefault("compaction_markers", [])
        if not isinstance(markers, list):
            return
        marker = {
            "trigger": str(state.get("trigger") or "automatic"),
            "summarized_count": int(state.get("summarized_count") or 0),
            "kept_recent_count": int(state.get("kept_recent_count") or 0),
            "saved_tokens": int(state.get("saved_tokens") or 0),
            "compacted_at": str(state.get("compacted_at") or ""),
        }
        markers.append(marker)
        del markers[:-8]

    def _runtime_diagnostics_payload(self) -> dict[str, Any]:
        state_store = getattr(self, "_runtime_state_store", {})
        metrics = (
            state_store.get("tool_metrics") if isinstance(state_store, dict) else None
        )
        safe_metrics = (
            {
                "started": int(metrics.get("started") or 0),
                "completed": int(metrics.get("completed") or 0),
                "failed": int(metrics.get("failed") or 0),
                "blocked": int(metrics.get("blocked") or 0),
                "awaiting_approval": int(metrics.get("awaiting_approval") or 0),
            }
            if isinstance(metrics, dict)
            else {
                "started": 0,
                "completed": 0,
                "failed": 0,
                "blocked": 0,
                "awaiting_approval": 0,
            }
        )
        memory_markers = (
            state_store.get("memory_markers") if isinstance(state_store, dict) else None
        )
        compaction_markers = (
            state_store.get("compaction_markers")
            if isinstance(state_store, dict)
            else None
        )
        hook_summary = (
            summarize_runtime_hooks_state(state_store)
            if isinstance(state_store, dict)
            else {}
        )
        policy_summary = (
            summarize_runtime_policy_state(state_store)
            if isinstance(state_store, dict)
            else {}
        )
        last_compaction = getattr(self, "_last_compaction_state", None)
        return {
            "tool_density": safe_metrics,
            "hooks": hook_summary,
            "policy": policy_summary,
            "memory": {
                "recent": [
                    item
                    for item in (
                        memory_markers if isinstance(memory_markers, list) else []
                    )
                    if isinstance(item, dict)
                ][-8:],
            },
            "compaction": {
                "recent": [
                    item
                    for item in (
                        compaction_markers
                        if isinstance(compaction_markers, list)
                        else []
                    )
                    if isinstance(item, dict)
                ][-6:],
                "latest": dict(last_compaction or {}) if last_compaction else None,
            },
        }

    def _make_runtime_context(
        self,
        *,
        execution_mode: str,
        conversation_id: uuid.UUID | None,
        turn_index: int | None = None,
        step_id: str | None = None,
        phase: str | None = None,
    ) -> RuntimeContext:
        return RuntimeContext(
            auth=self.auth,
            execution_mode=execution_mode,
            conversation_id=str(conversation_id) if conversation_id else None,
            turn_index=turn_index,
            step_id=step_id,
            phase=phase,
            state=self._runtime_state_store,
        )

    def _make_tool_runtime_context(
        self,
        *,
        execution_mode: str,
        conversation_id: uuid.UUID | None,
        turn_index: int | None,
        step_id: str | None,
        phase: str | None,
        tool_id: str | None = None,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
    ) -> ToolRuntimeContext:
        return ToolRuntimeContext(
            auth=self.auth,
            execution_mode=execution_mode,
            conversation_id=str(conversation_id) if conversation_id else None,
            turn_index=turn_index,
            step_id=step_id,
            phase=phase,
            tool_id=tool_id,
            tool_name=tool_name,
            tool_input=dict(tool_input or {}),
            state=self._runtime_state_store,
        )

    def _make_tool_context(
        self,
        *,
        conversation_id: uuid.UUID | None,
        mission_id: str | None = None,
        lane_id: str | None = None,
        temp_state_store: dict[str, Any] | None = None,
        tool_call_id: str | None = None,
    ) -> ToolContext:
        return ToolContext(
            tenant_id=self.auth.tenant_id,
            user_id=self.auth.user_id,
            conversation_id=conversation_id,
            mission_id=mission_id,
            lane_id=lane_id,
            temp_state_store=(temp_state_store if temp_state_store is not None else {}),
            tool_call_id=tool_call_id,
        )

    @staticmethod
    def _is_test_runner_call(tool_name: str, args: dict[str, Any] | None) -> bool:
        if tool_name != "bash" or not args:
            return False
        cmd = str(args.get("command") or "").strip().lower()
        return bool(
            re.search(r"\bpytest\b", cmd)
            or re.search(r"\bpython\s+-m\s+pytest\b", cmd)
            or re.search(r"\bpython\d*\s+-m\s+pytest\b", cmd)
            or re.search(r"\bnpm\s+test\b", cmd)
            or re.search(r"\bpnpm\s+test\b", cmd)
            or re.search(r"\byarn\s+test\b", cmd)
            or re.search(r"\bbun\s+test\b", cmd)
            or re.search(r"\bpython\s+-m\s+unittest\b", cmd)
            or re.search(r"\bpython\d*\s+-m\s+unittest\b", cmd)
        )

    async def stream_agent_loop(
        self,
        conversation_id: uuid.UUID | None = None,
        user_message: str | None = None,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        is_subagent: bool = False,
        resume_step_id: str | None = None,
        resume_tool_id: str | None = None,
        resume_approved: bool = False,
    ) -> AsyncIterator[AgentStepEvent]:
        """Compatibility wrapper for the older subagent path."""
        prompt = user_message or ""
        if is_subagent:
            prompt = (
                "SPECIALIZED MISSION CELL:\n"
                f"{prompt}\n\n"
                "Return a concise high-density summary. Do not expose chain of thought."
            )
        async for event in self.execute(
            conversation_id=conversation_id,
            user_message=prompt,
            previous_messages=None,
            note_content=None,
            thinking_enabled=thinking_enabled,
            web_search_enabled=web_search_enabled,
        ):
            yield event

    async def execute(
        self,
        user_message: str,
        previous_messages: list[dict[str, Any]] | None = None,
        note_content: str | None = None,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        append_user_message: bool = True,
        run_control: Any | None = None,
        conversation_id: uuid.UUID | None = None,
        coding_contract: CodingMissionContract | None = None,
    ) -> AsyncGenerator[AgentStepEvent, None]:
        """Main autonomous loop with two-layer memory injection and auto-triggers."""
        active_run_control = run_control or getattr(self, "run_control", None)
        execution_mode = getattr(self, "execution_mode", "auto_review")
        effective_coding_contract = coding_contract or CodingMissionContract(
            objective=user_message,
            isolation_mode=str(
                getattr(self.settings, "deepspace_coding_isolation_mode", "container")
            ),
            container_image=getattr(
                self.settings, "deepspace_coding_container_image", "python:3.12-slim"
            ),
        )
        autonomy = AutonomyController(
            GoalContract.from_request(
                user_message,
                verification_commands=effective_coding_contract.verification_commands,
            )
        )
        if autonomy.goal.coding_task:
            self.tool_executor.coding_harness = CodingHarness(
                effective_coding_contract
            )
            activate_worktree = getattr(
                self.tool_executor, "activate_coding_worktree", None
            )
            autonomy.set_isolation_ready(
                bool(activate_worktree(self.tool_executor.coding_harness))
                if callable(activate_worktree)
                else True
            )
        else:
            self.tool_executor.coding_harness = None
        runtime_hooks = getattr(self, "runtime_hooks", None) or RuntimeHooks()
        runtime_policy = getattr(self, "runtime_policy", None) or RuntimePolicy()
        workspace_policy = getattr(self, "workspace_policy", None) or WorkspacePolicy()
        registry = MissionRegistry(self.settings, db=getattr(self, "db", None))
        previous_mission_id = getattr(self, "mission_id", None)
        previous_mission_registry = getattr(self, "mission_registry", None)
        auto_mission_id: str | None = None
        if autonomy.goal.coding_task and conversation_id and not previous_mission_id:
            auto_mission_id = str(uuid.uuid4())
            self.mission_id = auto_mission_id
            self.mission_registry = registry
            registry.register_mission(
                mission_id=auto_mission_id,
                tenant_id=str(self.auth.tenant_id),
                user_id=str(self.auth.user_id),
                objective=user_message,
                plan={
                    "planner_source": "agent_loop",
                    "graph": {"nodes": []},
                    "lanes": [],
                },
                parent_id=str(conversation_id),
                status="running",
                execution_mode=execution_mode,
                full_autonomy=registry.get_full_autonomy_enabled(
                    tenant_id=str(self.auth.tenant_id),
                    user_id=str(self.auth.user_id),
                    conversation_id=str(conversation_id),
                ),
            )
        self._reset_runtime_diagnostics(
            execution_mode=execution_mode,
            conversation_id=conversation_id,
        )
        step_id = str(int(time.time()))
        previous_parent_id = getattr(self.tool_executor, "current_parent_id", None)
        previous_tool_context = getattr(self.tool_executor, "tool_context", None)
        previous_workspace_mode = getattr(self, "workspace_mode", WorkspaceMode())
        tool_state_store: dict[str, Any] = {}
        if conversation_id is not None:
            self.tool_executor.current_parent_id = conversation_id
        self.tool_executor.tool_context = self._make_tool_context(
            conversation_id=conversation_id,
            temp_state_store=tool_state_store,
        )
        try:
            hooks_enabled = bool(
                getattr(self.settings, "deepspace_runtime_hooks_rollout_enabled", True)
            ) and registry.get_runtime_hooks_enabled(
                tenant_id=str(self.auth.tenant_id),
                user_id=str(self.auth.user_id),
                conversation_id=str(conversation_id) if conversation_id else None,
            )
            if not hooks_enabled:
                runtime_hooks = RuntimeHooks()
            pre_turn_context = self._make_runtime_context(
                execution_mode=execution_mode,
                conversation_id=conversation_id,
                step_id=step_id,
                phase="pre_turn",
            )
            pre_turn_payload = await runtime_hooks.run_pre_turn(
                pre_turn_context,
                {
                    "user_message": user_message,
                    "note_content": note_content,
                    "previous_messages": list(previous_messages or []),
                    "thinking_enabled": thinking_enabled,
                    "web_search_enabled": web_search_enabled,
                },
            )
            user_message = str(pre_turn_payload.get("user_message") or user_message)
            note_content = pre_turn_payload.get("note_content", note_content)
            if isinstance(pre_turn_payload.get("previous_messages"), list):
                previous_messages = pre_turn_payload["previous_messages"]
            thinking_enabled = bool(
                pre_turn_payload.get("thinking_enabled", thinking_enabled)
            )
            web_search_enabled = bool(
                pre_turn_payload.get("web_search_enabled", web_search_enabled)
            )
            workspace_mode_enabled = bool(
                getattr(self.settings, "deepspace_workspace_mode_rollout_enabled", True)
            ) and registry.get_workspace_mode_enabled(
                tenant_id=str(self.auth.tenant_id),
                user_id=str(self.auth.user_id),
                conversation_id=str(conversation_id) if conversation_id else None,
            )
            workspace_mode = (
                workspace_policy.resolve_mode(
                    auth=self.auth,
                    user_message=user_message,
                    note_content=note_content,
                )
                if workspace_mode_enabled
                else WorkspaceMode()
            )
            self.workspace_mode = workspace_mode
            if getattr(self.tool_executor, "tool_context", None) is not None:
                self.tool_executor.tool_context.set_state(
                    "workspace_mode",
                    workspace_mode.summary(),
                )
            fast_bootstrap_enabled = self._should_use_fast_bootstrap(
                user_message=user_message,
                previous_messages=previous_messages,
                note_content=note_content,
            )

            # --- LAYER 2: Load Persistent Memory at Start ---
            mem_facts = (
                []
                if fast_bootstrap_enabled
                else await self._load_memory_facts(query="*", limit=20)
            )
            self._record_memory_marker(
                kind="persistent_memory_bootstrap",
                count=len(mem_facts),
                fast_bootstrap=fast_bootstrap_enabled,
            )
            memory_context = self._format_memory_context(mem_facts)
            _ = self.llm
            context_limit = self.context_limit
            model_name = self.model_name
            provider_type = self.provider_type
            reasoning_profile = reasoning_capabilities(
                provider_type,
                model_name,
                base_url=self.base_url,
            )
            effective_thinking_enabled = bool(thinking_enabled) and bool(
                reasoning_profile.get("supports_reasoning")
            )
            effective_web_search_enabled = bool(web_search_enabled)
            reported_context_limit = self.reported_context_limit

            system_prompt = (
                f"{self._base_system_instruction()}\n\nUSER PERSISTENT KNOWLEDGE:\n{memory_context}"
                "\n\nAUTO-MEMORY RULE: If you discover a new project pattern, user preference, or "
                "mission-critical fact, use the 'memory_write' tool immediately."
                "\n\nOPENCHAT AUTONOMY RULES:\n"
                "- Use web_search automatically when the user's request depends on current, recent, "
                "live, or externally verifiable information.\n"
                "- If web search is unavailable, proceed with the best possible answer and explicitly "
                "say that live web access was unavailable.\n"
                "- Thinking is automatic when the selected model supports it; do not expose chain of "
                "thought to the user."
            )
            if workspace_mode.enabled:
                system_prompt = (
                    f"{system_prompt}\n\n{workspace_mode.instruction_block()}"
                )

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            if note_content:
                messages.append(
                    {"role": "system", "content": f"WORKSPACE CONTEXT:\n{note_content}"}
                )
            if previous_messages:
                messages.extend(
                    previous_messages[-(4 if fast_bootstrap_enabled else 10) :]
                )
            if append_user_message:
                messages.append({"role": "user", "content": user_message})

            current_turn_tool_calls: dict[int, dict[str, Any]] = {}
            turn_count = 0
            current_phase = "autonomous"  # LLM decides its own approach

            # --- Phase 2: Dynamic MCP Tool Discovery ---
            available_tools = list(ALL_TOOLS)

            from sqlalchemy import select
            from app.services.deepspace.execution.agent_tools import build_dynamic_mcp_tool

            # Native installed MCP servers are the only dynamic MCP source for
            # DeepSpace. Legacy connector rows remain available to their own
            # sync APIs but are not injected into the agent tool registry.
            if getattr(self, "db", None) is not None:
                from app.integrations.models.mcp_server import MCPServer
                native_servers = self.db.execute(
                    select(MCPServer).where(
                        MCPServer.tenant_id == self.auth.tenant_id,
                        MCPServer.user_id == self.auth.user_id,
                        MCPServer.enabled.is_(True),
                    )
                ).scalars().all()
                for server in native_servers:
                    for raw_tool in (server.config or {}).get("mcp_tools_cache", []):
                        if not isinstance(raw_tool, dict):
                            continue
                        raw_tool = {**raw_tool, "server_id": str(server.id)}
                        dynamic_tool = build_dynamic_mcp_tool(
                            server.id, raw_tool, server_name=str(server.config.get("vendor_slug") or server.name)
                        )
                        available_tools.append(dynamic_tool)
                        self.tool_executor.dynamic_tools[dynamic_tool.name] = dynamic_tool
            # ------------------------------------------

            if self.restricted_tools:
                available_tools = [
                    tool
                    for tool in available_tools
                    if tool.name in self.restricted_tools
                ]
            if not effective_web_search_enabled:
                available_tools = [
                    tool for tool in available_tools if tool.name != "web_search"
                ]

            # Planning is now LLM-driven - no automatic preflight planning
            # The LLM decides whether to create plans using the enter_plan_mode tool
            # or by creating its own planning approach dynamically

            # Long-running continuation is controlled by the supervisor.  A
            # legacy explicit setting may still provide a mission-specific
            # ceiling, but the historical fixed 12-turn limit is gone.
            configured_steps = self._max_execution_steps()
            current_mission_id = getattr(self, "mission_id", None)
            supervisor = AdaptiveExecutionSupervisor(
                mission_id=current_mission_id,
                max_turns=configured_steps,
                max_seconds=3600.0,
                checkpoint=(
                    lambda state: getattr(self, "mission_registry", None).save_checkpoint(
                        current_mission_id,
                        status="running",
                        next_action="continue model execution",
                        budget={"turns": state.get("turn"), "elapsed_seconds": state.get("elapsed_seconds")},
                    )
                    if getattr(self, "mission_registry", None) and current_mission_id
                    else None
                ),
            )
            should_continue = True
            final_status = "completed"
            direct_answer_emitted = False
            emitted_turn_signatures: set[str] = set()

            while should_continue and supervisor.can_continue(
                cancelled=self._run_control_cancelled(active_run_control)
            ):
                turn_count += 1
                supervisor.observe(turn=turn_count, progress=True)
                step_id = uuid.uuid4().hex
                try:
                    yield AgentStepEvent(
                        type="step_start",
                        data={
                            "turn_index": turn_count,
                            "step_id": step_id,
                            "status": "running",
                            "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                        },
                    )
                    if self._run_control_cancelled(active_run_control):
                        yield AgentStepEvent(
                            type="tool_error",
                            data={
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "error": "Execution cancelled by user.",
                                "timestamp": datetime.now(tz=UTC)
                                .isoformat()
                                .replace("+00:00", "Z"),
                                "runtime_diagnostics": self._runtime_diagnostics_payload(),
                            },
                        )
                        return

                    # --- SaaS METRICS: Send Context Usage to Frontend ---
                    raw_context = json.dumps(messages)
                    current_tokens = len(raw_context) // 4  # Basic estimation
                    usage_pct = (
                        min(current_tokens / max(reported_context_limit, 1), 1.0)
                        if isinstance(reported_context_limit, int)
                        and reported_context_limit > 0
                        else 0.0
                    )

                    yield AgentStepEvent(
                        type="agent_status",
                        data={
                            "turn_index": turn_count,
                            "step_id": step_id,
                            "context_usage": usage_pct,
                            "context_limit": reported_context_limit,
                            "context_limit_source": self.context_limit_source,
                            "context_used_tokens": current_tokens,
                            "context_remaining_tokens": (
                                max(reported_context_limit - current_tokens, 0)
                                if isinstance(reported_context_limit, int)
                                and reported_context_limit > 0
                                else None
                            ),
                            "token_count": current_tokens,
                            "model_name": model_name,
                            "provider_type": provider_type,
                            "execution_mode": execution_mode,
                            "bootstrap_mode": (
                                "fast" if fast_bootstrap_enabled else "full"
                            ),
                            "phase": current_phase,
                            "timestamp": datetime.now(tz=UTC)
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "active_tools": (
                                [
                                    tc["function"]["name"]
                                    for tc in current_turn_tool_calls.values()
                                ]
                                if current_turn_tool_calls
                                else []
                            ),
                            "runtime_diagnostics": self._runtime_diagnostics_payload(),
                        },
                    )
                    self._run_control_touch(
                        active_run_control,
                        status="running",
                        last_event_type="agent_status",
                        step_count=turn_count,
                    )

                    # Assemble context and call model
                    current_turn_content = []
                    current_turn_tool_calls = {}
                    announced_tool_call_ids: set[str] = set()
                    turn_start_at = time.perf_counter()
                    thinking_start_at = None
                    active_coding_harness = getattr(self.tool_executor, "coding_harness", None)
                    if active_coding_harness is not None:
                        estimated_tokens = estimate_messages_tokens(messages)
                        active_coding_harness.record_usage(
                            tokens=estimated_tokens,
                            # Conservative provider-agnostic estimate; provider
                            # usage metadata can replace this later.
                            cost_usd=estimated_tokens * 0.00002,
                        )
                        if (
                            active_coding_harness.tokens_used > active_coding_harness.contract.max_tokens
                            or active_coding_harness.cost_usd >= active_coding_harness.contract.max_cost_usd
                        ):
                            yield AgentStepEvent(
                                type="autonomy_decision",
                                data={
                                    "kind": "stop",
                                    "reason": "coding token or cost budget exhausted",
                                    "status": "blocked",
                                },
                            )
                            should_continue = False
                            final_status = "blocked"
                            break

                    request = ChatGenerateRequest(
                        model=self.model_name or self.settings.llm_model,
                        messages=messages,
                        temperature=0.1,
                        max_tokens=8192,
                        base_url=self.base_url or self.settings.llm_api_base_url,
                        api_key=self.api_key,
                        tools=[t.to_openai_tool() for t in available_tools],
                        reasoning_enabled=effective_thinking_enabled,
                        metadata={
                            "provider_type": self.provider_type
                            or self.settings.llm_provider,
                            "timeout_seconds": float(
                                self.settings.provider_timeout_seconds
                            ),
                        },
                    )

                    async for event in self._stream_llm_events_with_timeout(request):
                        if self._run_control_cancelled(active_run_control):
                            yield AgentStepEvent(
                                type="tool_error",
                                data={
                                    "error": "Execution cancelled by user.",
                                    "runtime_diagnostics": self._runtime_diagnostics_payload(),
                                },
                            )
                            return
                        if event["type"] == "thinking":
                            # Reduce "thinking spam":
                            # - Only emit a single thinking event per LLM turn.
                            # - Suppress thinking emissions during the optional preflight planning phase.
                            if thinking_start_at is None:
                                thinking_start_at = time.perf_counter()
                            if str(current_phase).strip() != "planning":
                                yield AgentStepEvent(
                                    type="agent_thinking",
                                    data={
                                        "text": event["text"],
                                        "turn_index": turn_count,
                                        "step_id": step_id,
                                        "status": "running",
                                        "timestamp": datetime.now(tz=UTC)
                                        .isoformat()
                                        .replace("+00:00", "Z"),
                                        "phase": current_phase,
                                    },
                                )
                        elif event["type"] == "delta":
                            text = event["text"]
                            candidate = "".join(current_turn_content) + text
                            # Some providers repeat an identical completion
                            # after an autonomy-gate continuation.  Preserve
                            # streaming for new content, but do not replay a
                            # previously emitted answer to the client.
                            duplicate = any(
                                previous.startswith(candidate)
                                for previous in emitted_turn_signatures
                            )
                            current_turn_content.append(text)
                            if not duplicate:
                                yield AgentStepEvent(
                                    type="answer_delta",
                                    data={
                                        "text": text,
                                        "turn_index": turn_count,
                                        "step_id": step_id,
                                        "timestamp": datetime.now(tz=UTC)
                                        .isoformat()
                                        .replace("+00:00", "Z"),
                                    },
                                )
                        elif event["type"] == "tool_calls_delta":
                            for tc_delta in event["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                if idx not in current_turn_tool_calls:
                                    current_turn_tool_calls[idx] = {
                                        "id": tc_delta.get("id"),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                fn_delta = tc_delta.get("function", {})
                                if fn_delta.get("name"):
                                    current_turn_tool_calls[idx]["function"][
                                        "name"
                                    ] += fn_delta["name"]
                                if fn_delta.get("arguments"):
                                    current_turn_tool_calls[idx]["function"][
                                        "arguments"
                                    ] += fn_delta["arguments"]

                                tool_call = current_turn_tool_calls[idx]
                                tool_call_id = str(
                                    tool_call.get("id")
                                    or tc_delta.get("id")
                                    or f"call_{idx}"
                                )
                                tool_call["id"] = tool_call_id
                                tool_name = str(
                                    tool_call["function"].get("name") or ""
                                ).strip()

                                if (
                                    not tool_name
                                    or tool_call_id in announced_tool_call_ids
                                ):
                                    continue
                                effective_tier = self.tool_executor.get_effective_tier(
                                    tool_name
                                )
                                if (
                                    effective_tier >= 2
                                    or tool_name == "ask_user_question"
                                ):
                                    continue
                                announced_tool_call_ids.add(tool_call_id)
                                yield AgentStepEvent(
                                    type="tool_start",
                                    data={
                                        "turn_index": turn_count,
                                        "step_id": step_id,
                                        "tool_id": tool_call_id,
                                        "tool_name": tool_name,
                                        "tool_input": self._parse_partial_tool_arguments(
                                            tool_call["function"].get("arguments")
                                        ),
                                        "permission_level": "auto",
                                        "tier": effective_tier,
                                        "phase": current_phase,
                                        "status": "running",
                                        "started_at": datetime.now(tz=UTC)
                                        .isoformat()
                                        .replace(
                                            "+00:00",
                                            "Z",
                                        ),
                                        "timestamp": datetime.now(tz=UTC)
                                        .isoformat()
                                        .replace("+00:00", "Z"),
                                    },
                                )

                    if thinking_start_at is not None:
                        thinking_duration = int(
                            (time.perf_counter() - thinking_start_at) * 1000
                        )
                        yield AgentStepEvent(
                            type="agent_thinking",
                            data={
                                "turn_index": turn_count,
                                "duration_ms": thinking_duration,
                                "status": "completed",
                            },
                        )

                    content = "".join(current_turn_content).strip()
                    if content:
                        emitted_turn_signatures.add(content)
                    tool_calls_list = list(current_turn_tool_calls.values())
                    if not tool_calls_list and content:
                        tool_calls_list = self._parse_textual_tool_calls(content)

                    if not tool_calls_list and content:
                        completion = autonomy.completion(final_text=content)
                        if completion.kind.value != "finish" and supervisor.can_continue():
                            messages.append({"role": "assistant", "content": content})
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "AUTONOMY GATE: the task is not verified yet. "
                                        f"{completion.reason}. Use the available tools to produce evidence, "
                                        "run the required verification, and only then report completion."
                                    ),
                                }
                            )
                            yield AgentStepEvent(
                                type="autonomy_gate",
                                data={"decision": completion.to_dict(), "status": "continue"},
                            )
                            continue
                        if completion.kind.value != "finish":
                            final_status = "blocked"
                            content = (
                                "I could not safely mark this task complete because the completion "
                                f"requirements were not met: {completion.reason}."
                            )
                        # The controller, not the model alone, authorizes completion.
                        direct_answer_context = self._make_runtime_context(
                            execution_mode=execution_mode,
                            conversation_id=conversation_id,
                            turn_index=turn_count,
                            step_id=step_id,
                            phase=current_phase,
                        )
                        await runtime_hooks.run_pre_answer_finalize(
                            direct_answer_context,
                            {
                                "content": content,
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "finalized": False,
                            },
                        )
                        await runtime_hooks.run_post_turn(
                            direct_answer_context,
                            {
                                "content": content,
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "finalized": False,
                            },
                        )
                        yield AgentStepEvent(
                            type="answer_done",
                            data={"total_steps": turn_count, "status": final_status},
                        )
                        direct_answer_emitted = True
                        self._run_control_touch(
                            active_run_control,
                            status=final_status,
                            last_event_type="answer_done",
                            step_count=turn_count,
                        )
                        should_continue = False  # LLM decided to stop
                        break

                    if not tool_calls_list:
                        # LLM returned neither tools nor content - safety break
                        should_continue = False
                        break

                    # --- STEP 4 & 5: Parallel Safe vs Sequential ---
                    parallel_safe = []
                    sequential = []
                    blocked_results = []
                    pause_for_permission = False

                    for tc in tool_calls_list:
                        parsed = self._parse_tool_call(tc)
                        if not parsed:
                            continue

                        base_tier = self.tool_executor.get_effective_tier(parsed.name)
                        if parsed.name == "ask_user_question":
                            yield AgentStepEvent(
                                type="ask_user_question",
                                data={
                                    "turn_index": turn_count,
                                    "step_id": step_id,
                                    "tool_id": parsed.id,
                                    "tool_name": parsed.name,
                                    "tool_input": parsed.arguments,
                                    "tier": base_tier,
                                    "message": "Question for you.",
                                },
                            )
                            pause_for_permission = True
                            sequential.append((tc, parsed))
                            continue

                        tool_context = self._make_tool_runtime_context(
                            execution_mode=execution_mode,
                            conversation_id=conversation_id,
                            turn_index=turn_count,
                            step_id=step_id,
                            phase=current_phase,
                            tool_id=parsed.id,
                            tool_name=parsed.name,
                            tool_input=parsed.arguments,
                        )
                        pre_tool_payload = await runtime_hooks.run_pre_tool(
                            tool_context,
                            {
                                "tool_name": parsed.name,
                                "tool_input": dict(parsed.arguments),
                                "tier": base_tier,
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "tool_id": parsed.id,
                            },
                        )
                        override_tool_name = str(
                            pre_tool_payload.get("tool_name") or parsed.name
                        ).strip()
                        override_tool_input = (
                            dict(pre_tool_payload.get("tool_input") or parsed.arguments)
                            if isinstance(pre_tool_payload.get("tool_input"), dict)
                            else parsed.arguments
                        )
                        parsed = ToolCallRequest(
                            id=parsed.id,
                            name=override_tool_name,
                            arguments=override_tool_input,
                        )
                        tool_context.tool_name = parsed.name
                        tool_context.tool_input = dict(parsed.arguments)
                        base_tier = self.tool_executor.get_effective_tier(parsed.name)
                        tool_definition = TOOL_MAP.get(parsed.name) or getattr(self.tool_executor, "dynamic_tools", {}).get(parsed.name)
                        decision = runtime_policy.assess_tool_call(
                            mode=execution_mode,  # type: ignore[arg-type]
                            tool_name=parsed.name,
                            tier=base_tier,
                            args=parsed.arguments,
                            workspace_mode=workspace_mode,
                            context_state=self._runtime_state_store,
                            tool_contract=getattr(tool_definition, "contract", None),
                        )
                        effective_tier = self.tool_executor.get_effective_tier(
                            parsed.name
                        )
                        started_at = (
                            datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
                        )
                        if decision.should_block:
                            self._increment_tool_metric("blocked")
                            blocked_output = f"SECURITY BLOCK: {decision.reason}"
                            yield AgentStepEvent(
                                type="observing",
                                data={
                                    "turn_index": turn_count,
                                    "step_id": step_id,
                                    "tool_id": parsed.id,
                                    "tool_name": parsed.name,
                                    "tool_input": parsed.arguments,
                                    "summary": f"Blocked unsafe action: {decision.reason}",
                                    "success": False,
                                    "observed_at": started_at,
                                    "timestamp": started_at,
                                    "phase": current_phase,
                                    "status": "failed",
                                    "runtime_diagnostics": self._runtime_diagnostics_payload(),
                                },
                            )
                            blocked_results.append(
                                (
                                    tc,
                                    parsed,
                                    type(
                                        "BlockedToolResult",
                                        (),
                                        {
                                            "success": False,
                                            "output": blocked_output,
                                        },
                                    )(),
                                    0,
                                )
                            )
                            self._run_control_touch(
                                active_run_control,
                                status="running",
                                last_event_type="security_block",
                                last_event_message=decision.reason,
                                last_tool_name=parsed.name,
                                last_tool_id=parsed.id,
                                step_count=turn_count,
                            )
                            await runtime_hooks.run_tool_error(
                                tool_context,
                                {
                                    "tool_name": parsed.name,
                                    "tool_input": dict(parsed.arguments),
                                    "error": decision.reason,
                                    "error_kind": "security_block",
                                    "turn_index": turn_count,
                                    "step_id": step_id,
                                    "tool_id": parsed.id,
                                },
                            )
                            continue

                        if decision.requires_human_approval:
                            self._increment_tool_metric("awaiting_approval")
                            yield AgentStepEvent(
                                type="permission_request",
                                data={
                                    "turn_index": turn_count,
                                    "step_id": step_id,
                                    "tool_id": parsed.id,
                                    "tool_name": parsed.name,
                                    "tool_input": parsed.arguments,
                                    "tier": effective_tier,
                                    "execution_mode": execution_mode,
                                    "message": f"SECURITY BLOCK: {decision.reason}",
                                    "risk_class": getattr(decision.tool_contract, "risk_class", None),
                                    "tool_contract": decision.tool_contract.to_dict() if decision.tool_contract is not None else None,
                                    "phase": current_phase,
                                    "status": "awaiting_approval",
                                    "timestamp": datetime.now(tz=UTC)
                                    .isoformat()
                                    .replace("+00:00", "Z"),
                                    "runtime_diagnostics": self._runtime_diagnostics_payload(),
                                },
                            )
                            pause_for_permission = True
                            sequential.append((tc, parsed))
                            continue

                        permission_level = (
                            "approved" if execution_mode == "full_access" else "auto"
                        )
                        self._increment_tool_metric("started")
                        if parsed.id not in announced_tool_call_ids:
                            yield AgentStepEvent(
                                type="tool_start",
                                data={
                                    "turn_index": turn_count,
                                    "step_id": step_id,
                                    "tool_id": parsed.id,
                                    "tool_name": parsed.name,
                                    "tool_input": parsed.arguments,
                                    "permission_level": permission_level,
                                    "tier": effective_tier,
                                    "execution_mode": execution_mode,
                                    "started_at": started_at,
                                    "timestamp": started_at,
                                    "phase": current_phase,
                                    "status": "running",
                                    "runtime_diagnostics": self._runtime_diagnostics_payload(),
                                },
                            )
                        if base_tier <= 1:
                            parallel_safe.append((tc, parsed))
                        else:
                            sequential.append((tc, parsed))

                    if pause_for_permission:
                        return  # Loop pauses here for HITL

                    # --- STEP 5: Parallel Execution (Promise.all equivalent) ---
                    tool_event_queue: asyncio.Queue[AgentStepEvent] = asyncio.Queue()

                    async def emit_tool_event(
                        event_type: str,
                        data: dict[str, Any],
                        queue: asyncio.Queue[AgentStepEvent] = tool_event_queue,
                    ) -> None:
                        await queue.put(AgentStepEvent(type=event_type, data=data))

                    async def run_tool(
                        tc_info,
                        *,
                        turn_index: int = turn_count,
                        current_step_id: str = step_id,
                    ):
                        tc_dict, p = tc_info
                        tool_context = self._make_tool_runtime_context(
                            execution_mode=execution_mode,
                            conversation_id=conversation_id,
                            turn_index=turn_index,
                            step_id=current_step_id,
                            phase=current_phase,
                            tool_id=p.id,
                            tool_name=p.name,
                            tool_input=p.arguments,
                        )
                        t0 = time.monotonic()
                        execute_kwargs: dict[str, Any] = {
                            "background_tasks": self.background_tasks,
                        }
                        if self._is_test_runner_call(p.name, p.arguments):
                            await emit_tool_event(
                                "agent_testing",
                                {
                                    "turn_index": turn_index,
                                    "step_id": current_step_id,
                                    "tool_id": p.id,
                                    "tool_name": p.name,
                                    "tool_input": p.arguments,
                                    "started_at": datetime.now(tz=UTC)
                                    .isoformat()
                                    .replace("+00:00", "Z"),
                                    "timestamp": datetime.now(tz=UTC)
                                    .isoformat()
                                    .replace("+00:00", "Z"),
                                    "phase": "testing",
                                    "status": "running",
                                },
                            )
                        execute_signature = inspect.signature(
                            self.tool_executor.execute
                        )
                        if "conversation_id" in execute_signature.parameters:
                            execute_kwargs["conversation_id"] = conversation_id
                        if "tool_context" in execute_signature.parameters:
                            execute_kwargs["tool_context"] = self._make_tool_context(
                                conversation_id=conversation_id,
                                temp_state_store=tool_state_store,
                                tool_call_id=p.id,
                            )
                        if "event_sink" in execute_signature.parameters:

                            async def sink(payload: dict[str, Any]) -> None:
                                text = str(payload.get("text") or "")
                                if not text:
                                    return
                                await emit_tool_event(
                                    "tool_delta",
                                    {
                                        "turn_index": turn_index,
                                        "step_id": current_step_id,
                                        "tool_id": p.id,
                                        "tool_name": p.name,
                                        "tool_input": p.arguments,
                                        "text": text,
                                        "stream": payload.get("stream"),
                                        "bash_id": payload.get("bash_id"),
                                        "timestamp": datetime.now(tz=UTC)
                                        .isoformat()
                                        .replace("+00:00", "Z"),
                                        "status": "running",
                                    },
                                )

                            execute_kwargs["event_sink"] = sink
                        res = await self.tool_executor.execute(
                            p.name, p.arguments, **execute_kwargs
                        )
                        result_data = getattr(res, "data", None)
                        autonomy_decision = autonomy.observe(
                            {
                                "tool_name": p.name,
                                "tool_input": dict(p.arguments),
                                "success": bool(res.success),
                                "output": str(res.output)[:12000],
                                **(dict(result_data) if isinstance(result_data, dict) else {}),
                                "changed_files": (result_data or {}).get("changed_files")
                                if isinstance(result_data, dict)
                                else None,
                            }
                        )
                        mission_id = getattr(self, "mission_id", None)
                        mission_registry = getattr(self, "mission_registry", None)
                        if mission_id and mission_registry:
                            mission_registry.append_event(
                                mission_id,
                                event_type="tool_observation",
                                data={
                                    "tool_name": p.name,
                                    "success": bool(res.success),
                                    "output": str(res.output)[:4000],
                                    "decision": autonomy_decision.to_dict(),
                                },
                                idempotency_key=f"{mission_id}:tool:{p.id}",
                                node_id=p.id,
                            )
                            mission_registry.append_event(
                                mission_id,
                                event_type="autonomy_decision",
                                data=autonomy_decision.to_dict(),
                                idempotency_key=f"{mission_id}:decision:{p.id}",
                            )
                            if autonomy_decision.kind.value == "repair":
                                mission_registry.invalidate_plan_branch(
                                    mission_id,
                                    node_id=p.id,
                                    reason=autonomy_decision.reason,
                                )
                                mission_registry.create_repair_node(
                                    mission_id,
                                    failed_node_id=p.id,
                                    reason=autonomy_decision.reason,
                                )
                            elif autonomy_decision.kind.value == "replan":
                                mission_registry.append_event(
                                    mission_id,
                                    event_type="plan_replanned",
                                    data={"failed_node_id": p.id, "reason": autonomy_decision.reason},
                                    idempotency_key=f"{mission_id}:replan:{p.id}:{len(autonomy.events)}",
                                )
                        self._runtime_state_store["autonomy_last_decision"] = autonomy_decision.to_dict()
                        coding_harness = getattr(self.tool_executor, "coding_harness", None)
                        if coding_harness is not None:
                            coding_harness.record_tool_result(
                                data=dict(result_data or {}),
                                output=str(res.output),
                                success=bool(res.success),
                            )
                        self._record_tool_result_metric(success=res.success)
                        result = (tc_dict, p, res, int((time.monotonic() - t0) * 1000))
                        hook_payload = {
                            "tool_name": p.name,
                            "tool_input": dict(p.arguments),
                            "output": str(res.output)[:8000],
                            "success": res.success,
                            "duration_ms": result[3],
                            "turn_index": turn_index,
                            "step_id": current_step_id,
                            "tool_id": p.id,
                        }
                        if res.success:
                            await runtime_hooks.run_post_tool(
                                tool_context, hook_payload
                            )
                        else:
                            await runtime_hooks.run_tool_error(
                                tool_context,
                                {
                                    **hook_payload,
                                    "error": str(res.output)[:8000],
                                    "error_kind": "tool_failure",
                                },
                            )
                        if self._is_test_runner_call(p.name, p.arguments):
                            await emit_tool_event(
                                (
                                    "agent_verifying"
                                    if res.success
                                    else "agent_self_correct"
                                ),
                                {
                                    "turn_index": turn_index,
                                    "step_id": current_step_id,
                                    "tool_id": p.id,
                                    "tool_name": p.name,
                                    "tool_input": p.arguments,
                                    "success": res.success,
                                    "output": str(res.output)[:8000],
                                    "duration_ms": result[3],
                                    "completed_at": datetime.now(tz=UTC)
                                    .isoformat()
                                    .replace("+00:00", "Z"),
                                    "timestamp": datetime.now(tz=UTC)
                                    .isoformat()
                                    .replace("+00:00", "Z"),
                                    "phase": "testing",
                                    "status": "completed" if res.success else "failed",
                                },
                            )
                        return result

                    parallel_tasks = [
                        asyncio.create_task(run_tool(ex)) for ex in parallel_safe
                    ]
                    parallel_results = []
                    pending_parallel = set(parallel_tasks)
                    while pending_parallel:
                        done_parallel, pending_parallel = await asyncio.wait(
                            pending_parallel,
                            timeout=0.05,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        while not tool_event_queue.empty():
                            yield await tool_event_queue.get()
                        for task in done_parallel:
                            parallel_results.append(await task)

                    # --- STEP 5: Sequential Execution (Side-effects) ---
                    sequential_results = []
                    for ex in sequential:
                        res = await run_tool(ex)
                        while not tool_event_queue.empty():
                            yield await tool_event_queue.get()
                        sequential_results.append(res)

                    while not tool_event_queue.empty():
                        yield await tool_event_queue.get()

                    # --- STEP 6: Feed all results back ---
                    all_results = (
                        blocked_results + parallel_results + sequential_results
                    )
                    messages.append(
                        {
                            "role": "assistant",
                            "content": content or None,
                            "tool_calls": [r[0] for r in all_results],
                        }
                    )
                    for tc_dict, p, res, dur in all_results:
                        yield AgentStepEvent(
                            type="tool_result",
                            data={
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "tool_id": p.id,
                                "tool_name": p.name,
                                "tool_input": p.arguments,
                                "success": res.success,
                                "output": res.output[:8000],
                                "duration_ms": dur,
                                "completed_at": datetime.now(tz=UTC)
                                .isoformat()
                                .replace("+00:00", "Z"),
                                "timestamp": datetime.now(tz=UTC)
                                .isoformat()
                                .replace("+00:00", "Z"),
                                "status": "completed" if res.success else "failed",
                                "phase": current_phase,
                                "runtime_diagnostics": self._runtime_diagnostics_payload(),
                            },
                        )
                        yield AgentStepEvent(
                            type="observing",
                            data={
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "tool_id": p.id,
                                "tool_name": p.name,
                                "tool_input": p.arguments,
                                "summary": self._build_observation_summary(
                                    p.name,
                                    res.output,
                                    res.success,
                                ),
                                "success": res.success,
                                "observed_at": datetime.now(tz=UTC)
                                .isoformat()
                                .replace(
                                    "+00:00",
                                    "Z",
                                ),
                                "timestamp": datetime.now(tz=UTC)
                                .isoformat()
                                .replace("+00:00", "Z"),
                                "status": "completed",
                                "phase": current_phase,
                                "runtime_diagnostics": self._runtime_diagnostics_payload(),
                            },
                        )
                        tool_content = res.output
                        if not res.success or any(err in str(res.output) for err in ["SyntaxError", "Compilation Failed", "Traceback", "AssertionError", "ERROR:"]):
                            tool_content += (
                                "\n\n[SYSTEM GUIDANCE - SELF-REPAIR STATE ACTIVATED]\n"
                                "The previous action returned errors or failed execution. Please analyze the traceback or error logs carefully, "
                                "cross-reference the modified code files, check for import mismatches or syntax issues, "
                                "and write a repair step to correct the root cause immediately."
                            )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": p.id,
                                "content": tool_content,
                            }
                        )
                        self._run_control_touch(
                            active_run_control,
                            status="running",
                            last_event_type="observing",
                            last_event_message=res.output[:1000],
                            last_tool_name=p.name,
                            last_tool_id=p.id,
                            step_count=turn_count,
                        )

                    autonomy_decision = self._runtime_state_store.get("autonomy_last_decision")
                    if isinstance(autonomy_decision, dict):
                        yield AgentStepEvent(
                            type="autonomy_decision",
                            data={
                                "turn_index": turn_count,
                                "step_id": step_id,
                                **autonomy_decision,
                            },
                        )
                        if autonomy_decision.get("kind") == "stop":
                            should_continue = False
                        elif autonomy_decision.get("kind") == "replan":
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "AUTONOMY REPLAN: repeated work was detected without new evidence. "
                                        "Change strategy, inspect the current state, and avoid repeating the same action."
                                    ),
                                }
                            )

                    # --- STEP 7: Check context size (Compaction) ---
                    if self._is_near_limit(
                        messages,
                        threshold=self.AUTO_COMPACTION_THRESHOLD,
                    ):
                        before_tokens = estimate_messages_tokens(messages)
                        messages = await self._compact_context(messages)
                        compacted_state = dict(self._last_compaction_state or {})
                        compacted_state.setdefault("before_tokens", before_tokens)
                        self._record_compaction_marker(compacted_state)
                        self._run_control_touch(
                            active_run_control,
                            last_event_type="context_compaction",
                            step_count=turn_count,
                        )
                        yield AgentStepEvent(
                            type="step_summary",
                            data={
                                "turn_index": turn_count,
                                "step_id": step_id,
                                "message": "Context compacted to preserve runtime headroom.",
                                "status": "completed",
                                "timestamp": datetime.now(tz=UTC)
                                .isoformat()
                                .replace("+00:00", "Z"),
                                "phase": current_phase,
                                "compaction_state": compacted_state,
                                "runtime_diagnostics": self._runtime_diagnostics_payload(),
                            },
                        )

                except Exception as e:
                    logger.error(f"Agent Loop failure: {str(e)}", exc_info=True)
                    await runtime_hooks.run_tool_error(
                        self._make_tool_runtime_context(
                            execution_mode=execution_mode,
                            conversation_id=conversation_id,
                            turn_index=turn_count,
                            step_id=step_id,
                            phase=current_phase,
                        ),
                        {
                            "error": str(e),
                            "error_kind": "agent_loop_failure",
                            "turn_index": turn_count,
                            "step_id": step_id,
                        },
                    )
                    yield AgentStepEvent(
                        type="tool_error",
                        data={
                            "turn_index": turn_count,
                            "error": str(e),
                            "runtime_diagnostics": self._runtime_diagnostics_payload(),
                        },
                    )
                    break

            if should_continue and supervisor.stop_reason:
                final_status = "blocked"

            # If the loop exits without a direct final answer, fall back to synthesis.
            full_answer_parts: list[str] = []
            final_text = "".join(full_answer_parts).strip()
            if not final_text:
                synthesized_text = await self._synthesize_final_answer(
                    messages=messages,
                    user_message=user_message,
                    note_content=note_content,
                    memory_context=memory_context,
                    thinking_enabled=effective_thinking_enabled,
                )
                final_text = (
                    synthesized_text
                    or "I completed the available agent steps, but the provider did not return a visible final answer."
                )
            finalize_context = self._make_runtime_context(
                execution_mode=execution_mode,
                conversation_id=conversation_id,
                turn_index=turn_count,
                step_id=step_id,
                phase="completed",
            )
            finalize_payload = await runtime_hooks.run_pre_answer_finalize(
                finalize_context,
                {
                    "content": final_text,
                    "turn_index": turn_count,
                    "step_id": step_id,
                    "finalized": True,
                },
            )
            final_text = str(finalize_payload.get("content") or final_text)

            completion = autonomy.completion(final_text=final_text)
            if completion.kind.value != "finish":
                final_status = "blocked"
                if autonomy.goal.coding_task:
                    final_text = (
                        "Task not verified. I stopped before claiming completion: "
                        f"{completion.reason}."
                    )

            checkpoint_registry = getattr(self, "mission_registry", None)
            checkpoint_mission_id = getattr(self, "mission_id", None)
            if checkpoint_registry and checkpoint_mission_id:
                checkpoint_registry.save_checkpoint(
                    checkpoint_mission_id,
                    status=final_status,
                    next_action="resume from checkpoint" if final_status == "blocked" else "completed",
                    budget={"turns": turn_count, "supervisor_stop_reason": supervisor.stop_reason},
                    final_output=final_text,
                )
                if final_status in {"blocked", "failed"}:
                    try:
                        checkpoint_registry.touch_mission(
                            checkpoint_mission_id,
                            status=final_status,
                            last_event_type="executor_budget_stop",
                            last_event_message="Executor stopped; checkpoint continuation is available.",
                        )
                    except ValueError:
                        pass
                    mission_snapshot = checkpoint_registry.get_mission(checkpoint_mission_id)
                    if mission_snapshot and mission_snapshot.get("full_autonomy"):
                        try:
                            if checkpoint_registry.schedule_continuation(checkpoint_mission_id):
                                from app.worker.tasks_deepspace import (
                                    continue_full_autonomy_mission,
                                )

                                continue_full_autonomy_mission.apply_async(
                                    args=[checkpoint_mission_id], countdown=5
                                )
                        except Exception:  # noqa: BLE001
                            logger.exception("Failed to schedule direct-agent continuation")

            yield AgentStepEvent(
                type="step_finish",
                data={
                    "turn_index": turn_count,
                    "step_id": step_id,
                    "status": final_status,
                    "timestamp": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
                    "phase": "completed",
                },
            )
            yield AgentStepEvent(
                type="step_summary",
                data={
                    "turn_index": turn_count,
                    "step_id": step_id,
                    "message": "Task complete." if final_status == "completed" else "Task stopped before verification.",
                    "status": final_status,
                    "timestamp": datetime.now(tz=UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "phase": "completed",
                    "runtime_diagnostics": self._runtime_diagnostics_payload(),
                },
            )
            # Direct streamed replies already have an answer_done terminal
            # event.  Do not emit a second synthetic final_answer for those
            # replies; synthesized/tool-driven runs still receive it.
            if not direct_answer_emitted:
                yield AgentStepEvent(
                    type="final_answer",
                    data={
                        "content": final_text,
                        "timestamp": datetime.now(tz=UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "runtime_diagnostics": self._runtime_diagnostics_payload(),
                    },
                )
            self._run_control_touch(
                active_run_control,
                status=final_status,
                last_event_type="final_answer",
                last_event_message=final_text[:1000],
                step_count=turn_count,
            )
            await runtime_hooks.run_post_turn(
                finalize_context,
                {
                    "content": final_text,
                    "turn_index": turn_count,
                    "step_id": step_id,
                    "finalized": True,
                },
            )
        finally:
            active_coding_harness = getattr(self.tool_executor, "coding_harness", None)
            if active_coding_harness is not None:
                active_coding_harness.stop_container()
            if auto_mission_id:
                try:
                    registry.touch_mission(
                        auto_mission_id,
                        status="completed" if locals().get("final_status") == "completed" else "blocked",
                        last_event_type="mission_finished",
                        last_event_message=(
                            "Coding mission completed with evidence."
                            if locals().get("final_status") == "completed"
                            else "Coding mission stopped before verified completion."
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to finalize autonomous coding mission.", exc_info=True)
            self.mission_id = previous_mission_id
            self.mission_registry = previous_mission_registry
            self.workspace_mode = previous_workspace_mode
            self.tool_executor.current_parent_id = previous_parent_id
            self.tool_executor.tool_context = previous_tool_context

    async def run(
        self,
        query_text: str,
        previous_messages: list[dict[str, Any]] | None = None,
        note_content: str | None = None,
        thinking_enabled: bool = True,
        web_search_enabled: bool = True,
        append_user_message: bool = True,
        coding_contract: CodingMissionContract | None = None,
    ) -> AsyncIterator[AgentStepEvent]:
        """Compatibility wrapper used by the DeepSpace service stream path."""
        async for event in self.execute(
            user_message=query_text,
            previous_messages=previous_messages,
            note_content=note_content,
            thinking_enabled=thinking_enabled,
            web_search_enabled=web_search_enabled,
            append_user_message=append_user_message,
            coding_contract=coding_contract,
        ):
            yield event

    @trace_async("deepspace.model.generate")
    async def _generate_with_retry(self, request: ChatGenerateRequest) -> Any:
        import random

        provider_circuit = getattr(self, "_provider_circuit", None)
        if provider_circuit is None:
            provider_circuit = CircuitBreaker()
            self._provider_circuit = provider_circuit
        max_retries = 5
        initial_backoff = 2.0
        backoff = initial_backoff
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                try:
                    provider_circuit.before_call()
                except Exception:
                    if last_error is not None:
                        raise last_error from None
                    raise
                result = await asyncio.to_thread(self.llm.generate, request)
                provider_circuit.record_success()
                return result
            except StopAsyncIteration:
                return
            except (ProviderRequestError, Exception) as e:
                last_error = e
                status_code = getattr(e, "status_code", None)
                is_transient = False
                if isinstance(e, ProviderRequestError):
                    is_transient = e.status_code in (429, 500, 502, 503, 504)
                elif status_code in (429, 500, 502, 503, 504):
                    is_transient = True

                if not is_transient and (
                    "rate limit" in str(e).lower()
                    or "429" in str(e)
                    or "too many requests" in str(e).lower()
                ):
                    is_transient = True

                if is_transient and attempt < max_retries:
                    sleep_time = backoff + random.uniform(0, 1.0)
                    logger.warning(
                        "Encountered rate limit or transient error (%s) during generate. Retrying in %.2f seconds (attempt %d/%d)...",
                        str(status_code or e),
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(sleep_time)
                    backoff *= 2.0
                else:
                    if is_transient:
                        provider_circuit.record_failure()
                    raise

    async def _synthesize_final_answer(
        self,
        *,
        messages: list[dict[str, Any]],
        user_message: str,
        note_content: str | None,
        memory_context: str,
        thinking_enabled: bool,
    ) -> str | None:
        synthesis_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "FINAL SYNTHESIS MODE: Return only the user-facing answer based on the work "
                    "already performed. Do not mention hidden reasoning, internal planning, or "
                    "that this is a fallback. Keep the answer concise, concrete, and useful."
                ),
            }
        ]
        if note_content:
            synthesis_messages.append(
                {"role": "system", "content": f"WORKSPACE CONTEXT:\n{note_content}"}
            )
        if memory_context.strip():
            synthesis_messages.append(
                {"role": "system", "content": f"PERSISTENT MEMORY:\n{memory_context}"}
            )
        synthesis_messages.extend(messages[-16:])
        if user_message.strip():
            synthesis_messages.append({"role": "user", "content": user_message})

        request = ChatGenerateRequest(
            model=self.model_name or self.settings.llm_model,
            messages=synthesis_messages,
            temperature=0.0,
            max_tokens=1024,
            base_url=self.base_url or self.settings.llm_api_base_url,
            api_key=self.api_key,
            tools=[],
            reasoning_enabled=thinking_enabled,
            metadata={
                "provider_type": self.provider_type or self.settings.llm_provider,
                "timeout_seconds": float(self.settings.provider_timeout_seconds),
            },
        )

        try:
            result = await self._generate_with_retry(request)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Final answer synthesis failed: %s", exc, exc_info=True)
            return None

        text = (result.content or "").strip()
        return text[:4000] if text else None

    @trace_async_generator("deepspace.model.stream")
    async def _stream_llm_events_with_timeout(
        self, request: ChatGenerateRequest
    ) -> AsyncIterator[dict[str, Any]]:
        import random

        stream_timeout_seconds = float(self.settings.provider_timeout_seconds) * (
            self.STREAM_IDLE_TIMEOUT_MULTIPLIER
        )
        max_retries = 5
        initial_backoff = 2.0
        backoff = initial_backoff

        for attempt in range(max_retries + 1):
            stream = self.llm.stream_generate_events(request)
            try:
                # Attempt to get the first event to ensure request succeeds
                first_event = await asyncio.wait_for(
                    anext(stream), timeout=stream_timeout_seconds
                )
                yield first_event

                # Consume the rest of the stream
                try:
                    while True:
                        event = await asyncio.wait_for(
                            anext(stream), timeout=stream_timeout_seconds
                        )
                        yield event
                except StopAsyncIteration:
                    return
                except TimeoutError:
                    logger.warning(
                        "LLM provider stream stalled for %.1f seconds; falling back to synthesis.",
                        stream_timeout_seconds,
                    )
                    return
                # Successfully finished stream
                break
            except StopAsyncIteration:
                return
            except (ProviderRequestError, Exception) as e:
                aclose = getattr(stream, "aclose", None)
                if callable(aclose):
                    with contextlib.suppress(Exception):
                        await aclose()

                status_code = getattr(e, "status_code", None)
                is_transient = False
                if isinstance(e, ProviderRequestError):
                    is_transient = e.status_code in (429, 500, 502, 503, 504)
                elif status_code in (429, 500, 502, 503, 504):
                    is_transient = True

                if not is_transient and (
                    "rate limit" in str(e).lower()
                    or "429" in str(e)
                    or "too many requests" in str(e).lower()
                ):
                    is_transient = True

                # Also treat connection/DNS resolution and timeout errors as transient to allow retries
                err_str = str(e).lower()
                if not is_transient and (
                    "temporary failure in name resolution" in err_str
                    or "name resolution" in err_str
                    or "connect" in err_str
                    or "timeout" in err_str
                    or "connection" in err_str
                    or "host" in err_str
                    or "socket" in err_str
                    or "network" in err_str
                ):
                    is_transient = True

                if is_transient and attempt < max_retries:
                    sleep_time = backoff + random.uniform(0, 1.0)
                    logger.warning(
                        "Rate limit or transient error (%s) on stream. Retrying in %.2f seconds (attempt %d/%d)...",
                        str(status_code or e),
                        sleep_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(sleep_time)
                    backoff *= 2.0
                else:
                    raise

    def _is_near_limit(self, messages: list[dict], threshold: float = 0.85) -> bool:
        """Heuristic check for context window usage."""
        total_chars = sum(len(str(m.get("content") or "")) for m in messages)
        return total_chars > (self.context_limit * threshold)

    @property
    def last_compaction_state(self) -> dict[str, Any] | None:
        last_compaction = getattr(self, "_last_compaction_state", None)
        return dict(last_compaction) if last_compaction else None

    @property
    def runtime_diagnostics(self) -> dict[str, Any]:
        return self._runtime_diagnostics_payload()

    async def force_compact(self, conversation_id: uuid.UUID) -> dict[str, Any]:
        """Persist a compacted conversation snapshot for future DeepSpace turns."""
        repo = ChatRepository(self.db)
        messages = list(
            repo.get_messages(
                tenant_id=self.auth.tenant_id,
                conversation_id=conversation_id,
                user_id=self.auth.user_id,
                kind="deepspace",
            )
        )
        if not messages:
            return {"status": "noop", "compaction": None}

        snapshot_source: list[dict[str, Any]] = []
        for message in messages:
            active_version = getattr(message, "active_version", None)
            content = (
                active_version.content
                if active_version is not None
                and isinstance(active_version.content, str)
                else message.content
            )
            if not str(content or "").strip():
                continue
            snapshot_source.append(
                {
                    "id": str(message.id),
                    "message_id": str(message.id),
                    "role": str(message.role),
                    "content": str(content),
                }
            )

        anchor_message_id = str(messages[-1].id) if messages else None
        compaction_state = build_conversation_compaction_state(
            base_messages=snapshot_source,
            trigger="manual",
            anchor_message_id=anchor_message_id,
        )
        if compaction_state is None:
            return {"status": "noop", "compaction": None}

        target_message = next(
            (msg for msg in reversed(messages) if msg.role == "assistant"), None
        )
        if target_message is None:
            target_message = messages[-1]
        target_active_version = getattr(target_message, "active_version", None)
        target_content = (
            target_active_version.content
            if target_active_version is not None
            and isinstance(target_active_version.content, str)
            else target_message.content
        )
        target_metadata = dict(getattr(target_message, "metadata_json", {}) or {})
        target_metadata["conversation_compaction"] = compaction_state.to_metadata()
        repo.create_message_version(
            tenant_id=self.auth.tenant_id,
            message_id=target_message.id,
            content=str(target_content or ""),
            metadata_json=target_metadata,
            source_type="manual_compaction",
            activate=True,
        )
        self.db.commit()
        self._last_compaction_state = compaction_state.to_metadata()
        return {"status": "compacted", "compaction": compaction_state.to_metadata()}

    async def _compact_context(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Compaction Rules:
        - Trigger at 85% context window usage
        - Preserve: system prompt, last 5 tool results, original task
        - Summarize: older turns
        - Re-inject: persistent memory
        """
        normalized_messages = [
            {
                "role": str(message.get("role") or "system"),
                "content": str(message.get("content") or ""),
            }
            for message in messages
            if str(message.get("content") or "").strip()
        ]
        system_prompts = [m for m in normalized_messages if m["role"] == "system"]
        original_task = [m for m in normalized_messages if m["role"] == "user"][:1]
        recent = normalized_messages[-10:]
        middle_candidates = normalized_messages[
            len(system_prompts) + len(original_task) : -10
        ]
        summary_prompt: dict[str, Any] | None = None
        if middle_candidates:
            summary_lines: list[str] = []
            for item in middle_candidates[-12:]:
                role = "User" if item["role"] == "user" else "Assistant"
                text = item["content"].replace("\n", " ").strip()
                if len(text) > 160:
                    text = f"{text[:157].rstrip()}..."
                summary_lines.append(f"- {role}: {text}")
            summary_prompt = {
                "role": "system",
                "content": "COMPACTED HISTORY SUMMARY:\n" + "\n".join(summary_lines),
            }

        # Re-inject persistent memory
        mem_facts = await self._load_memory_facts(query="*")
        mem_prompt = (
            {
                "role": "system",
                "content": "RE-INJECTED KNOWLEDGE:\n"
                + self._format_memory_context(mem_facts),
            }
            if mem_facts
            else None
        )

        logger.info("Context Compaction triggered. Compressing history.")
        compacted = system_prompts + original_task
        if summary_prompt is not None:
            compacted.append(summary_prompt)
        if mem_prompt is not None:
            compacted.append(mem_prompt)
        compacted.extend(recent)
        before_tokens = estimate_messages_tokens(normalized_messages)
        after_tokens = estimate_messages_tokens(compacted)
        self._last_compaction_state = {
            "version": 1,
            "trigger": "automatic",
            "compacted_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            "anchor_message_id": None,
            "summary": str(summary_prompt["content"]) if summary_prompt else "",
            "summarized_count": len(middle_candidates),
            "kept_recent_count": len(recent),
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "saved_tokens": max(before_tokens - after_tokens, 0),
            "compacted_messages": compacted,
        }
        return compacted

    async def _load_memory_facts(
        self,
        *,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        cache_key = (str(self.auth.tenant_id), str(self.auth.user_id), query, limit)
        cached = self._get_cached_memory_bootstrap(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]
        memory_service = getattr(self.tool_executor, "memory", None)
        search_memories = getattr(memory_service, "search_memories", None)
        if not callable(search_memories):
            return []
        try:
            results = await search_memories(
                tenant_id=self.auth.tenant_id,
                user_id=self.auth.user_id,
                query=query,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "DeepSpace memory bootstrap unavailable; continuing without persisted memory: %s",
                exc,
                exc_info=True,
            )
            return []
        normalized_results = [item for item in results if isinstance(item, dict)]
        self._set_cached_memory_bootstrap(cache_key, normalized_results)
        return [dict(item) for item in normalized_results]

    @classmethod
    def _get_cached_memory_bootstrap(
        cls, cache_key: tuple[str, str, str, int]
    ) -> list[dict[str, Any]] | None:
        now = time.monotonic()
        with cls._memory_bootstrap_cache_lock:
            entry = cls._memory_bootstrap_cache.get(cache_key)
            if entry is None:
                return None
            if (now - entry.cached_at) > cls.MEMORY_BOOTSTRAP_CACHE_TTL_SECONDS:
                cls._memory_bootstrap_cache.pop(cache_key, None)
                return None
            return entry.facts

    @classmethod
    def _set_cached_memory_bootstrap(
        cls,
        cache_key: tuple[str, str, str, int],
        facts: list[dict[str, Any]],
    ) -> None:
        with cls._memory_bootstrap_cache_lock:
            cls._memory_bootstrap_cache[cache_key] = _MemoryBootstrapCacheEntry(
                cached_at=time.monotonic(),
                facts=[dict(item) for item in facts],
            )

    @staticmethod
    def _format_memory_context(mem_facts: list[dict[str, Any]]) -> str:
        return "\n".join(
            [
                f"- {fact['key']}: {fact['value']}"
                for fact in mem_facts
                if "key" in fact and "value" in fact
            ]
        )

    def _parse_tool_call(self, tc: dict[str, Any]) -> ToolCallRequest | None:
        try:
            fn = tc.get("function", {})
            if not isinstance(fn, dict):
                return None
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    parsed_args = json.loads(args)
                except json.JSONDecodeError:
                    parsed_args = self._parse_partial_tool_arguments(args)
            else:
                parsed_args = self._parse_partial_tool_arguments(args)
            return ToolCallRequest(
                id=tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                name=fn.get("name", ""),
                arguments=parsed_args,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _looks_like_textual_tool_call(content: str) -> bool:
        stripped = content.lstrip()
        prefix = stripped[:80].upper()
        if any(
            prefix.startswith(f"[{name}") or prefix.startswith(name)
            for name in TEXTUAL_TOOL_NAME_MAP
        ):
            return True
        lower_content = content.lower()
        if "<tool_code" in lower_content or "<tool_call" in lower_content:
            return True
        return False

    @staticmethod
    def _parse_xml_inner_tool_call(
        inner_content: str,
    ) -> tuple[str, dict[str, Any]] | None:
        inner = inner_content.strip()
        if not inner:
            return None

        # Try parsing as JSON first
        if inner.startswith("{") and inner.endswith("}"):
            try:
                data = json.loads(inner)
                if isinstance(data, dict):
                    name = data.get("name") or data.get("tool")
                    args = data.get("arguments") or data.get("args") or {}
                    if isinstance(name, str) and name:
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = AgentExecutor._parse_textual_tool_arguments(args)
                        if isinstance(args, dict):
                            normalized_name = name.strip()
                            if normalized_name.upper() in TEXTUAL_TOOL_NAME_MAP:
                                normalized_name = TEXTUAL_TOOL_NAME_MAP[
                                    normalized_name.upper()
                                ]
                            else:
                                normalized_name = normalized_name.lower()
                            return normalized_name, args
            except Exception:
                pass

        # Try parsing as function call style: name(args)
        first_paren = inner.find("(")
        if first_paren != -1:
            name = inner[:first_paren].strip()
            rest = inner[first_paren + 1 :].strip()
            if rest.endswith(")"):
                rest = rest[:-1].strip()
            args = AgentExecutor._parse_textual_tool_arguments(rest)
            if name and isinstance(args, dict):
                normalized_name = name
                if normalized_name.upper() in TEXTUAL_TOOL_NAME_MAP:
                    normalized_name = TEXTUAL_TOOL_NAME_MAP[normalized_name.upper()]
                else:
                    normalized_name = normalized_name.lower()
                return normalized_name, args

        return None

    @staticmethod
    def _parse_textual_tool_calls(content: str) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []

        # 1. Parse XML-style tool calls
        xml_matches = re.finditer(
            r"<(tool_code|tool_call)[^>]*>(.*?)(?:</\1>|$)",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for index, match in enumerate(xml_matches):
            inner_content = match.group(2)
            parsed_call = AgentExecutor._parse_xml_inner_tool_call(inner_content)
            if parsed_call:
                name, arguments = parsed_call
                tool_calls.append(
                    {
                        "id": f"xml_call_{index}_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments),
                        },
                    }
                )

        # 2. Parse original format textual tool calls
        matches = re.finditer(
            r"\[?\s*(ASK_USER_QUESTION|TODO_WRITE|ENTER_PLAN_MODE|MEMORY_WRITE)\s*\((.*?)\)\s*\]?\s*<?\s*TOOL_CALL_END",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        for index, match in enumerate(matches):
            raw_name = match.group(1).upper()
            tool_name = TEXTUAL_TOOL_NAME_MAP.get(raw_name)
            if not tool_name:
                continue
            arguments = AgentExecutor._parse_textual_tool_arguments(match.group(2))
            tool_calls.append(
                {
                    "id": f"text_call_{index}_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(arguments),
                    },
                }
            )
        return tool_calls

    @staticmethod
    def _parse_textual_tool_arguments(raw_arguments: str) -> dict[str, Any]:
        text = raw_arguments.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

        result: dict[str, Any] = {}
        assignment_pattern = re.compile(
            r'(?P<key>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<value>\[[^\]]*\]|\{[^}]*\}|".*?"|\'.*?\'|[^,]+)',
            flags=re.IGNORECASE | re.DOTALL,
        )
        for match in assignment_pattern.finditer(text):
            normalized_key = match.group("key").strip().lower()
            raw_value = match.group("value").strip()
            try:
                parsed_value = json.loads(raw_value)
            except json.JSONDecodeError:
                parsed_value = raw_value.strip("\"'")
            result[normalized_key] = parsed_value

        return result

    @staticmethod
    def _parse_partial_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str) or not raw_arguments.strip():
            return {}
        try:
            parsed = json.loads(raw_arguments)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return AgentExecutor._parse_textual_tool_arguments(raw_arguments)

    def _build_initial_messages(
        self,
        *,
        query_text: str,
        previous_messages: list[dict[str, Any]] | None,
        note_content: str | None,
    ) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": self._base_system_instruction()}]
        if note_content:
            messages.append(
                {"role": "system", "content": f"WORKSPACE CONTEXT:\n{note_content}"}
            )
        if previous_messages:
            messages.extend(previous_messages[-6:])
        messages.append({"role": "user", "content": query_text})
        return messages

    def _base_system_instruction(self) -> str:
        configured = getattr(self.settings, "system_rulebook", None)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return self.SYSTEM_INSTRUCTION

    def _is_complex_task(
        self,
        user_message: str,
        *,
        previous_messages: list[dict[str, str]] | None,
        note_content: str | None,
    ) -> bool:
        """Deprecated: LLM now decides complexity autonomously."""
        # The LLM determines if planning is needed; no hardcoded heuristics
        return False

    def _should_use_fast_bootstrap(
        self,
        *,
        user_message: str,
        previous_messages: list[dict[str, Any]] | None,
        note_content: str | None,
    ) -> bool:
        """Skip expensive memory bootstrap for isolated, conversational turns."""
        if previous_messages or note_content:
            return False
        text = str(user_message or "").strip().lower()
        if not text or len(text) > 240:
            return False
        coding_markers = (
            "code", "file", "repo", "repository", "implement", "fix", "test",
            "debug", "terminal", "command", "workspace", "migration",
        )
        return not any(marker in text for marker in coding_markers)

    async def _build_autonomous_plan(
        self,
        *,
        user_message: str,
        note_content: str | None,
        previous_messages: list[dict[str, str]] | None,
        memory_context: str,
        available_tools: list[Any],
    ) -> AsyncIterator[tuple[str, Any]]:
        """Deprecated: LLM now handles planning autonomously via tools."""
        # The LLM decides when and how to plan using enter_plan_mode tool
        # No automatic preflight planning
        yield "plan", "LLM-driven autonomous execution - no preflight plan needed."

    @property
    def llm(self):
        """Dynamic LLM provider resolver."""
        return self._resolve_runtime()
