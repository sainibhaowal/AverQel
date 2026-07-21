from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, cast

from sqlalchemy import select

from app.auth.dependencies import AuthContext
from app.core.config import Settings
from app.models.deepspace.agent_activity import AgentActivity
from app.integrations.models.connector import Connector, ConnectorStatus
from app.integrations.models.integration import Integration
from app.services.deepspace.execution.agent_executor import AgentExecutor
from app.services.deepspace.memory.memory_service import MemoryService, TodoService
from app.services.deepspace.missions.mission_registry import MissionControl, MissionRegistry
from app.services.deepspace.planning.mission_planner import MissionPlanner
from app.services.deepspace.subagents.subagent_manager import SubagentManager
from app.providers.services.types import ChatGenerateRequest
from app.query.services.answer_service import StreamEvent
from app.system.services.vitals_service import VitalsService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MissionLaneResult:
    lane_id: str
    lane_type: str
    status: str
    summary: str
    final_output: str
    metadata: dict[str, Any]


class MasterOrchestrator:
    """Federated coordinator for OpenChat, subagents, memory, and proactive work."""

    def __init__(
        self,
        *,
        db: Any,
        auth: AuthContext,
        settings: Settings,
        background_tasks: Any | None = None,
        agent_executor_cls: type[AgentExecutor] | None = None,
    ) -> None:
        self.db = db
        self.auth = auth
        self.settings = settings
        self.background_tasks = background_tasks
        self.agent_executor_cls = agent_executor_cls or AgentExecutor
        self.agent = self.agent_executor_cls(
            db=db,
            auth=auth,
            settings=settings,
            background_tasks=background_tasks,
        )
        self.registry = MissionRegistry(settings, db=db)
        self.subagents = SubagentManager(db, settings, auth)
        self.todo_service = TodoService(db, settings)
        self.memory_service = MemoryService(db, settings)
        self.planner = MissionPlanner(agent=self.agent, settings=settings)

    def _planner_mode_preference(self, conversation_id: uuid.UUID | None = None) -> str:
        if not bool(
            getattr(self.settings, "deepspace_structured_planner_rollout_enabled", True)
        ):
            return str(
                getattr(self.settings, "deepspace_default_planner_mode", "default")
            )
        return self.registry.get_planner_mode(
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            conversation_id=str(conversation_id) if conversation_id else None,
        )


    def _runtime_visibility_state(
        self,
        *,
        conversation_id: uuid.UUID | None = None,
        plan: dict[str, Any] | None = None,
        runtime_diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conversation_key = str(conversation_id) if conversation_id else None
        planner_mode = self._planner_mode_preference(conversation_id)
        runtime_hooks_enabled = False
        if bool(
            getattr(self.settings, "deepspace_runtime_hooks_rollout_enabled", True)
        ):
            runtime_hooks_enabled = self.registry.get_runtime_hooks_enabled(
                tenant_id=str(self.auth.tenant_id),
                user_id=str(self.auth.user_id),
                conversation_id=conversation_key,
            )
        subagent_profile = self.registry.get_subagent_profile(
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            conversation_id=conversation_key,
        )
        workspace_mode_enabled = self.registry.get_workspace_mode_enabled(
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            conversation_id=conversation_key,
        )
        planner_validation_status = "pending"
        planner_source = str((plan or {}).get("planner_source") or "").strip().lower()
        if planner_source == "model":
            planner_validation_status = "validated"
        elif planner_source == "system_support":
            planner_validation_status = "system_support"
        elif planner_source:
            planner_validation_status = "policy_fallback"

        planner_safety = (
            dict((plan or {}).get("safety") or {})
            if isinstance((plan or {}).get("safety"), dict)
            else {}
        )
        planner_diagnostics = {
            "source": planner_source or "pending",
            "mode": str((plan or {}).get("planner_mode") or planner_mode),
            "lane_count": int(
                planner_safety.get("lane_count") or len((plan or {}).get("lanes") or [])
            ),
            "parallel_limit": int((plan or {}).get("parallel_limit") or 0),
            "gated_actions_detected": bool(
                planner_safety.get("gated_actions_detected")
            ),
            "dynamic_fanout": int(planner_safety.get("dynamic_fanout") or 0),
        }
        diagnostics = dict(runtime_diagnostics or {})
        diagnostics.setdefault("planner", planner_diagnostics)

        return {
            "planner_mode": planner_mode,
            "planner_validation_status": planner_validation_status,
            "runtime_hooks_state": "active" if runtime_hooks_enabled else "disabled",
            "subagent_profile": subagent_profile,
            "subagent_profile_classification": (
                "preferred_profile"
                if subagent_profile and subagent_profile != "default"
                else "adaptive"
            ),
            "workspace_mode_enabled": workspace_mode_enabled,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _lane_visibility_metadata(
        lane: dict[str, Any],
        *,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(lane.get("metadata") or {})
        lane_type = str(lane.get("lane_type") or "")
        requested_type = lane.get("subagent_type")
        metadata.setdefault(
            "role",
            metadata.get("role")
            or ("primary" if lane_type == "main_chat" else lane_type),
        )
        metadata.setdefault("support_kind", metadata.get("support_kind") or lane_type)
        metadata.setdefault(
            "delegation_rationale",
            str(lane.get("prompt") or lane.get("title") or lane_type)[:280],
        )
        metadata.setdefault("requested_subagent_type", requested_type)
        if requested_type and "resolved_subagent_type" not in metadata:
            metadata["resolved_subagent_type"] = requested_type
        if extra:
            metadata.update(extra)
        return metadata

    @staticmethod
    def _lane_dependencies_met(
        lane: dict[str, Any],
        *,
        completed_lanes: set[str],
        blocked_lanes: set[str],
    ) -> bool:
        dependencies = [
            str(dep) for dep in lane.get("depends_on") or [] if str(dep).strip()
        ]
        blockers = [
            str(dep) for dep in lane.get("blocked_by") or [] if str(dep).strip()
        ]
        if any(dep in blocked_lanes for dep in dependencies + blockers):
            return False
        return all(dep in completed_lanes for dep in dependencies)

    @staticmethod
    def _lane_priority(lane: dict[str, Any]) -> tuple[int, int, str]:
        return (
            -int(lane.get("priority") or 0),
            len(lane.get("depends_on") or []),
            str(lane.get("lane_id") or ""),
        )

    @staticmethod
    def _lane_mutates_workspace(lane: dict[str, Any]) -> bool:
        lane_type = str(lane.get("lane_type") or "").lower()
        role = str((lane.get("metadata") or {}).get("role") or "").lower()
        subagent_type = str(lane.get("subagent_type") or "").lower()
        return lane_type in {"writer", "executor"} or role in {
            "implementer", "repair", "release", "writer", "executor"
        } or subagent_type in {"implementer", "repair", "release", "writer", "executor"}

    async def stream_mission(
        self,
        *,
        objective: str,
        note_content: str | None = None,
        previous_messages: list[dict[str, Any]] | None = None,
        conversation_id: uuid.UUID | None = None,
        execution_mode: str = "auto_review",
        await_approval: bool = True,
        mission_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        normalized_execution_mode = (
            "full_access"
            if str(execution_mode).strip().lower() == "full_access"
            else "auto_review"
        )
        start_time = perf_counter()

        existing_mission = None
        if mission_id:
            existing_mission = self.registry.get_mission(mission_id)

        if existing_mission:
            plan = existing_mission.get("plan") or {}
            normalized_execution_mode = (
                existing_mission.get("execution_mode") or normalized_execution_mode
            )
            objective = existing_mission.get("objective") or objective
            full_autonomy = bool(existing_mission.get("full_autonomy"))
        else:
            mission_id = str(uuid.uuid4())
            get_full_autonomy = getattr(self.registry, "get_full_autonomy_enabled", None)
            full_autonomy = bool(
                get_full_autonomy(
                    tenant_id=str(self.auth.tenant_id),
                    user_id=str(self.auth.user_id),
                    conversation_id=str(conversation_id) if conversation_id else None,
                )
                if callable(get_full_autonomy)
                else False
            )
            provisional_plan: dict[str, Any] = {
                "planner_source": "pending",
                "summary": "Planning mission graph.",
                "parallel_limit": 0,
                "signals": {},
                "approval_queue": [],
                "lanes": [],
                "graph": {},
            }
            register_kwargs = dict(
                mission_id=mission_id,
                tenant_id=str(self.auth.tenant_id),
                user_id=str(self.auth.user_id),
                objective=objective,
                plan=provisional_plan,
                parent_id=str(conversation_id) if conversation_id else None,
                status="planning",
                execution_mode=normalized_execution_mode,
                full_autonomy=full_autonomy,
            )
            try:
                self.registry.register_mission(**register_kwargs)
            except TypeError as exc:
                # Keep lightweight registry doubles/backward-compatible stores
                # usable while the durable registry accepts the new flag.
                if "full_autonomy" not in str(exc):
                    raise
                register_kwargs.pop("full_autonomy", None)
                self.registry.register_mission(**register_kwargs)

            yield StreamEvent(
                event="mission_start",
                data={
                    "mission_id": mission_id,
                    "objective": objective,
                    "plan": provisional_plan,
                    "execution_mode": normalized_execution_mode,
                    "full_autonomy": full_autonomy,
                    "planner_source": "pending",
                    "phase": "planning",
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id
                    ),
                },
            )
            self.registry.touch_mission(
                mission_id,
                status="planning",
                last_event_type="mission_start",
                last_event_message="Mission started.",
                runtime_state=self._runtime_visibility_state(
                    conversation_id=conversation_id
                ),
            )
            yield StreamEvent(
                event="mission_planning",
                data={
                    "mission_id": mission_id,
                    "status": "planning",
                    "message": "Building mission plan.",
                    "execution_mode": normalized_execution_mode,
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id
                    ),
                },
            )
            planner_mode = self._planner_mode_preference(conversation_id)
            events_queue = asyncio.Queue()

            async def on_planner_event(ev_type: str, ev_data: Any):
                if ev_type == "thinking":
                    await events_queue.put(
                        StreamEvent(
                            event="lane_agent_thinking",
                            data={
                                "mission_id": mission_id,
                                "lane_id": "planner",
                                "lane_type": "main_chat",
                                "text": ev_data,
                                "timestamp": datetime.now(tz=UTC)
                                .isoformat()
                                .replace("+00:00", "Z"),
                            },
                        )
                    )

            plan_task = asyncio.create_task(
                self.planner.build_plan(
                    objective=objective,
                    note_content=note_content,
                    execution_mode=normalized_execution_mode,
                    planner_mode=planner_mode,
                    on_event=on_planner_event,
                )
            )

            while not plan_task.done() or not events_queue.empty():
                try:
                    event = await asyncio.wait_for(events_queue.get(), timeout=0.05)
                    yield event
                except TimeoutError:
                    continue

            plan = await plan_task
            self.registry.touch_mission(
                mission_id,
                plan=plan,
                lane_states=plan.get("lanes", []),
                approval_queue=list(plan.get("approval_queue") or []),
                status="running",
                last_event_type="mission_planning",
                last_event_message="Mission planning completed.",
                runtime_state=self._runtime_visibility_state(
                    conversation_id=conversation_id,
                    plan=plan,
                ),
            )
            yield StreamEvent(
                event="mission_plan",
                data={
                    "mission_id": mission_id,
                    "plan": plan,
                    "execution_mode": normalized_execution_mode,
                    "planner_source": plan.get("planner_source"),
                    "planner_mode": plan.get("planner_mode"),
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id,
                        plan=plan,
                    ),
                },
            )
            self.registry.touch_mission(
                mission_id,
                status="running",
                last_event_type="mission_plan",
                last_event_message="Mission plan created.",
                runtime_state=self._runtime_visibility_state(
                    conversation_id=conversation_id,
                    plan=plan,
                ),
            )
            yield StreamEvent(
                event="mission_graph",
                data={
                    "mission_id": mission_id,
                    "graph": plan.get("graph", {}),
                    "signals": plan.get("signals", {}),
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id,
                        plan=plan,
                    ),
                },
            )
            self.registry.touch_mission(
                mission_id,
                status="running",
                last_event_type="mission_graph",
                last_event_message="Mission graph published.",
                runtime_state=self._runtime_visibility_state(
                    conversation_id=conversation_id,
                    plan=plan,
                ),
            )

        if existing_mission and str(existing_mission.get("status") or "") in {
            "ready",
            "blocked",
            "failed",
        }:
            self.registry.touch_mission(
                mission_id,
                status="running",
                last_event_type="mission_resume",
                last_event_message="Resuming mission from checkpoint.",
            )

        control = MissionControl(self.registry, mission_id)
        event_queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        lane_results: dict[str, MissionLaneResult] = {}
        lane_tasks: set[asyncio.Task[MissionLaneResult]] = set()
        active_write_lanes: set[str] = set()
        lane_specs = {
            str(lane.get("lane_id") or ""): lane for lane in plan.get("lanes") or []
        }
        launched_lanes: set[str] = set()
        completed_lanes: set[str] = set()
        blocked_lanes: set[str] = set()

        if existing_mission:
            lane_states = existing_mission.get("lane_states") or []
            approval_queue = existing_mission.get("approval_queue") or []
            for lane in lane_states:
                l_id = str(lane.get("lane_id") or "")
                l_status = str(lane.get("status") or "").lower()
                is_in_approval_queue = any(
                    str(item.get("lane_id") or "") == l_id for item in approval_queue
                )

                if l_status in {"completed", "failed", "cancelled"}:
                    launched_lanes.add(l_id)
                    completed_lanes.add(l_id)
                    lane_results[l_id] = MissionLaneResult(
                        lane_id=l_id,
                        lane_type=str(lane.get("lane_type") or ""),
                        status=str(lane.get("status") or "completed"),
                        summary=str(lane.get("summary") or ""),
                        final_output=str(lane.get("final_output") or ""),
                        metadata=dict(lane.get("metadata") or {}),
                    )
                elif l_status in {"blocked", "awaiting_approval"}:
                    if not is_in_approval_queue:
                        launched_lanes.add(l_id)
                        completed_lanes.add(l_id)
                        lane_state = lane_specs.get(l_id)
                        if lane_state is not None:
                            lane_state["status"] = "approved"
                    else:
                        launched_lanes.add(l_id)
                        blocked_lanes.add(l_id)
        mission_runtime_diagnostics: dict[str, Any] = {}
        pending_approval = False
        pending_approval_lane_id: str | None = None
        pending_approval_lane_type: str | None = None
        approval_declined = False
        mission_cancelled = False
        subagent_registry = getattr(self.subagents, "registry", None)
        planner_parallel_limit = int(plan.get("parallel_limit") or 0)
        default_parallel_limit = min(
            len(lane_specs) or 2,
            int(getattr(subagent_registry, "max_concurrency", 4)) + 3,
        )
        max_parallel_lanes = max(
            2,
            min(
                planner_parallel_limit or default_parallel_limit,
                default_parallel_limit,
            ),
        )

        async def emit(event: str, data: dict[str, Any]) -> None:
            await event_queue.put(StreamEvent(event=event, data=data))

        async def persist_lane_memory(
            *,
            lane_id: str,
            lane_type: str,
            summary: str,
            output: str,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            content = (output or summary or "").strip()
            if not content:
                return
            try:
                await self.memory_service.store_fact(
                    tenant_id=str(self.auth.tenant_id),
                    user_id=str(self.auth.user_id),
                    key=f"mission:{mission_id}:{lane_id}",
                    value=content[:4000],
                    scope="mission",
                    tags=["orchestration", "mission", lane_type],
                )
                if metadata:
                    await self.memory_service.store_fact(
                        tenant_id=str(self.auth.tenant_id),
                        user_id=str(self.auth.user_id),
                        key=f"mission:{mission_id}:{lane_id}:meta",
                        value=str(metadata)[:4000],
                        scope="mission",
                        tags=["orchestration", "mission", lane_type, "meta"],
                    )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Failed to persist orchestration lane memory for %s.",
                    lane_id,
                    exc_info=True,
                )

        async def launch_lane(lane: dict[str, Any]) -> None:
            lane_id = str(lane.get("lane_id") or "")
            lane_type = str(lane.get("lane_type") or "")
            if not lane_id or lane_id in launched_lanes:
                return
            launched_lanes.add(lane_id)
            self.registry.update_lane(mission_id, lane_id, status="running")
            lane_metadata = self._lane_visibility_metadata(lane)
            await emit(
                "lane_start",
                {
                    "mission_id": mission_id,
                    "lane_id": lane_id,
                    "lane_type": lane_type,
                    "title": lane.get("title") or lane_type,
                    "prompt": lane.get("prompt") or objective,
                    "depends_on": lane.get("depends_on") or [],
                    "metadata": lane_metadata,
                },
            )

            async def run_lane() -> MissionLaneResult:
                nonlocal mission_runtime_diagnostics
                lane_prompt = str(lane.get("prompt") or objective)
                start = perf_counter()
                try:
                    if lane_type == "main_chat":
                        collected: list[str] = []
                        step_count = 0
                        status = "completed"
                        lane_agent = self.agent_executor_cls(
                            db=self.db,
                            auth=self.auth,
                            settings=self.settings,
                            background_tasks=self.background_tasks,
                            execution_mode=normalized_execution_mode,
                            run_control=control,
                            mission_id=mission_id,
                            mission_registry=self.registry,
                        )
                        async for event in lane_agent.run(
                            query_text=objective,
                            previous_messages=previous_messages,
                            note_content=note_content,
                            thinking_enabled=True,
                            web_search_enabled=True,
                        ):
                            if control.is_cancelled():
                                await emit(
                                    "lane_error",
                                    {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "error": "Mission cancelled by user.",
                                    },
                                )
                                self.registry.update_lane(
                                    mission_id,
                                    lane_id,
                                    status="cancelled",
                                    error="Mission cancelled by user.",
                                )
                                return MissionLaneResult(
                                    lane_id=lane_id,
                                    lane_type=lane_type,
                                    status="cancelled",
                                    summary="Mission cancelled.",
                                    final_output="Mission cancelled.",
                                    metadata={"step_count": step_count},
                                )
                            step_count += 1
                            if event.type == "permission_request":
                                nonlocal pending_approval
                                nonlocal pending_approval_lane_id
                                nonlocal pending_approval_lane_type
                                pending_approval = True
                                pending_approval_lane_id = lane_id
                                pending_approval_lane_type = lane_type
                                approval_data = {
                                    "mission_id": mission_id,
                                    "lane_id": lane_id,
                                    "lane_type": lane_type,
                                    "message": str(
                                        event.data.get("message")
                                        or f"Approval needed for {event.data.get('tool_name') or 'tool'}."
                                    ),
                                    "tool_name": event.data.get("tool_name"),
                                    "tool_input": event.data.get("tool_input") or {},
                                    "metadata": {
                                        **lane_metadata,
                                        "runtime_diagnostics": event.data.get(
                                            "runtime_diagnostics"
                                        )
                                        or lane_agent.runtime_diagnostics,
                                    },
                                }
                                await emit("approval_request", approval_data)
                                self.registry.request_approval(
                                    mission_id, approval_data
                                )
                                status = "awaiting_approval"
                                self.registry.update_lane(
                                    mission_id,
                                    lane_id,
                                    status=status,
                                    metadata={"approval": event.data},
                                )
                                break

                            if event.type == "agent_thinking":
                                await emit(
                                    "lane_agent_thinking",
                                    {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "text": str(event.data.get("text") or ""),
                                        "turn_index": event.data.get("turn_index"),
                                        "duration_ms": event.data.get("duration_ms"),
                                        "status": event.data.get("status"),
                                        "metadata": lane_metadata,
                                    },
                                )
                            elif event.type == "tool_delta":
                                await emit(
                                    "lane_tool_delta",
                                    {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "tool_name": event.data.get("tool_name"),
                                        "tool_input": event.data.get("tool_input"),
                                        "turn_index": event.data.get("turn_index"),
                                        "metadata": lane_metadata,
                                    },
                                )
                            elif event.type == "answer_delta":
                                text = str(event.data.get("text") or "")
                                if text:
                                    collected.append(text)
                                    await emit(
                                        "lane_delta",
                                        {
                                            "mission_id": mission_id,
                                            "lane_id": lane_id,
                                            "lane_type": lane_type,
                                            "text": text,
                                            "metadata": lane_metadata,
                                        },
                                    )
                            elif event.type == "observing":
                                await emit(
                                    "lane_observation",
                                    {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "summary": str(event.data.get("summary") or ""),
                                        "tool_name": event.data.get("tool_name"),
                                        "metadata": {
                                            **lane_metadata,
                                            "runtime_diagnostics": event.data.get(
                                                "runtime_diagnostics"
                                            )
                                            or lane_agent.runtime_diagnostics,
                                        },
                                    },
                                )
                            elif event.type == "final_answer":
                                content = str(event.data.get("content") or "").strip()
                                if content:
                                    collected.append(content)
                                answer_status = str(event.data.get("status") or "")
                                if answer_status in {"blocked", "failed", "cancelled"}:
                                    status = answer_status
                            elif event.type == "step_finish":
                                step_status = str(event.data.get("status") or "")
                                if step_status in {"blocked", "failed", "cancelled"}:
                                    status = step_status
                            elif event.type == "step_summary":
                                await emit(
                                    "lane_step_summary",
                                    {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "message": str(event.data.get("message") or ""),
                                        "metadata": {
                                            **lane_metadata,
                                            "compaction_state": event.data.get(
                                                "compaction_state"
                                            ),
                                            "runtime_diagnostics": event.data.get(
                                                "runtime_diagnostics"
                                            )
                                            or lane_agent.runtime_diagnostics,
                                        },
                                    },
                                )
                            else:
                                await emit(
                                    f"lane_{event.type}",
                                    {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "metadata": lane_metadata,
                                        **event.data,
                                    },
                                )

                        output = "".join(collected).strip()
                        if not output:
                            output = "OpenChat lane completed without a visible final answer."
                        lane_runtime_diagnostics = lane_agent.runtime_diagnostics
                        mission_runtime_diagnostics = lane_runtime_diagnostics
                        lane_result_metadata = {
                            **lane_metadata,
                            "runtime_diagnostics": lane_runtime_diagnostics,
                            "compaction_state": lane_agent.last_compaction_state,
                            "tool_density": lane_runtime_diagnostics.get(
                                "tool_density"
                            ),
                            "lane_lifecycle_summary": {
                                "step_count": step_count,
                                "status": status,
                                "elapsed_ms": int((perf_counter() - start) * 1000),
                            },
                        }
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status=status,
                            summary=output[:1000],
                            final_output=output[:8000],
                            step_count=step_count,
                            metadata=lane_result_metadata,
                        )
                        await persist_lane_memory(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            summary=output[:1000],
                            output=output,
                            metadata=lane_result_metadata,
                        )
                        await emit(
                            "lane_result",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "status": status,
                                "summary": output[:1000],
                                "output": output[:8000],
                                "step_count": step_count,
                                "metadata": lane_result_metadata,
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status=status,
                            summary=output[:1000],
                            final_output=output[:8000],
                            metadata=lane_result_metadata,
                        )

                    if lane_type in {"research", "analysis", "writer", "executor"}:
                        parent_lineage_id = (
                            conversation_id
                            if conversation_id is not None
                            else uuid.UUID(mission_id)
                        )
                        result = await self.subagents.spawn_and_execute(
                            str(lane.get("subagent_type") or lane_type),
                            lane_prompt,
                            parent_id=parent_lineage_id,
                            execution_mode=normalized_execution_mode,
                            conversation_id=conversation_id,
                        )
                        output = str(result.output or "").strip()
                        status = "completed" if result.success else "failed"
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status=status,
                            summary=output[:1000],
                            final_output=output[:8000],
                            metadata=self._lane_visibility_metadata(
                                lane,
                                extra={
                                    **(result.data or {}),
                                    "lane_lifecycle_summary": {
                                        "status": status,
                                        "elapsed_ms": int(
                                            (perf_counter() - start) * 1000
                                        ),
                                    },
                                },
                            ),
                        )
                        subagent_metadata = self._lane_visibility_metadata(
                            lane,
                            extra={
                                **(result.data or {}),
                                "lane_lifecycle_summary": {
                                    "status": status,
                                    "elapsed_ms": int((perf_counter() - start) * 1000),
                                },
                            },
                        )
                        await persist_lane_memory(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            summary=output[:1000],
                            output=output,
                            metadata=subagent_metadata,
                        )
                        await emit(
                            "lane_result",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "status": status,
                                "summary": output[:1000],
                                "output": output[:8000],
                                "metadata": subagent_metadata,
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status=status,
                            summary=output[:1000],
                            final_output=output[:8000],
                            metadata=subagent_metadata,
                        )

                    if lane_type == "memory":
                        await self.memory_service.store_fact(
                            tenant_id=str(self.auth.tenant_id),
                            user_id=str(self.auth.user_id),
                            key=f"mission:{mission_id}:memory",
                            value=lane_prompt[:4000],
                            scope="mission",
                            tags=["orchestration", "mission", "memory"],
                        )
                        self.todo_service.upsert_task(
                            tenant_id=str(self.auth.tenant_id),
                            user_id=str(self.auth.user_id),
                            content=lane_prompt[:4000],
                            active_form=lane_prompt[:4000],
                            status="in_progress",
                            priority=75,
                            thread_id=str(conversation_id) if conversation_id else None,
                            metadata_json={
                                "source": "master_orchestrator",
                                "mission_id": mission_id,
                                "lane_type": lane_type,
                            },
                        )
                        output = "Memory and work ledger updated."
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status="completed",
                            summary=output,
                            final_output=output,
                            metadata=self._lane_visibility_metadata(
                                lane,
                                extra={
                                    "memory_persisted": True,
                                    "lane_lifecycle_summary": {
                                        "status": "completed",
                                        "elapsed_ms": int(
                                            (perf_counter() - start) * 1000
                                        ),
                                    },
                                },
                            ),
                        )
                        await persist_lane_memory(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            summary=output,
                            output=output,
                        )
                        await emit(
                            "lane_result",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "status": "completed",
                                "summary": output,
                                "output": output,
                                "metadata": self._lane_visibility_metadata(
                                    lane,
                                    extra={"memory_persisted": True},
                                ),
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status="completed",
                            summary=output,
                            final_output=output,
                            metadata=self._lane_visibility_metadata(
                                lane,
                                extra={"memory_persisted": True},
                            ),
                        )

                    if lane_type == "proactive":
                        task_id = self.todo_service.upsert_task(
                            tenant_id=str(self.auth.tenant_id),
                            user_id=str(self.auth.user_id),
                            content=f"Orchestration follow-up: {lane_prompt[:500]}",
                            active_form=f"Orchestration follow-up: {lane_prompt[:500]}",
                            status="pending",
                            priority=60,
                            thread_id=str(conversation_id) if conversation_id else None,
                            metadata_json={
                                "source": "master_orchestrator",
                                "mission_id": mission_id,
                                "lane_type": lane_type,
                            },
                            automation_json={
                                "action_type": "agent_prompt",
                                "schedule_type": "once",
                                "prompt": lane_prompt[:2000],
                                "source": "master_orchestrator",
                            },
                            is_recurring=False,
                            enabled=True,
                        )
                        output_parts: list[str] = []
                        proactive_status = "completed"
                        proactive_runtime_diagnostics: dict[str, Any] | None = None
                        try:
                            lane_agent = AgentExecutor(
                                db=self.db,
                                auth=self.auth,
                                settings=self.settings,
                                background_tasks=self.background_tasks,
                                execution_mode=normalized_execution_mode,
                                run_control=control,
                                mission_id=mission_id,
                                mission_registry=self.registry,
                            )
                            async for event in lane_agent.run(
                                query_text=lane_prompt,
                                previous_messages=previous_messages,
                                note_content=note_content,
                                thinking_enabled=True,
                                web_search_enabled=True,
                            ):
                                if event.type == "permission_request":
                                    proactive_status = "awaiting_approval"
                                    approval_data = {
                                        "mission_id": mission_id,
                                        "lane_id": lane_id,
                                        "lane_type": lane_type,
                                        "message": str(
                                            event.data.get("message")
                                            or "Approval needed for proactive follow-up."
                                        ),
                                        "tool_name": event.data.get("tool_name"),
                                        "tool_input": event.data.get("tool_input")
                                        or {},
                                        "metadata": {
                                            **lane_metadata,
                                            "runtime_diagnostics": event.data.get(
                                                "runtime_diagnostics"
                                            )
                                            or lane_agent.runtime_diagnostics,
                                        },
                                    }
                                    await emit("approval_request", approval_data)
                                    self.registry.request_approval(
                                        mission_id, approval_data
                                    )
                                    break
                                if event.type == "answer_delta":
                                    text = str(event.data.get("text") or "")
                                    if text:
                                        output_parts.append(text)
                                elif event.type == "final_answer":
                                    content = str(event.data.get("content") or "")
                                    if content:
                                        output_parts.append(content)
                                elif event.type == "step_summary" and not output_parts:
                                    message = str(event.data.get("message") or "")
                                    if message:
                                        output_parts.append(message)
                            proactive_runtime_diagnostics = (
                                lane_agent.runtime_diagnostics
                            )
                        except Exception as exc:  # noqa: BLE001
                            proactive_status = "failed"
                            output_parts = [str(exc)]
                        proactive_metadata = self._lane_visibility_metadata(
                            lane,
                            extra={
                                "task_id": task_id,
                                "runtime_diagnostics": proactive_runtime_diagnostics,
                                "lane_lifecycle_summary": {
                                    "status": proactive_status,
                                    "elapsed_ms": int((perf_counter() - start) * 1000),
                                },
                            },
                        )
                        output = (
                            "".join(output_parts).strip()
                            or f"Proactive task queued: {task_id}"
                        )
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status=proactive_status,
                            summary=output,
                            final_output=output,
                            metadata=proactive_metadata,
                        )
                        await persist_lane_memory(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            summary=output,
                            output=output,
                            metadata=proactive_metadata,
                        )
                        await emit(
                            "lane_result",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "status": proactive_status,
                                "summary": output,
                                "output": output,
                                "task_id": task_id,
                                "metadata": proactive_metadata,
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status=proactive_status,
                            summary=output,
                            final_output=output,
                            metadata=proactive_metadata,
                        )

                    if lane_type == "connector":
                        connector_names = list(
                            lane.get("metadata", {}).get("connectors") or []
                        )
                        task_id = self.todo_service.upsert_task(
                            tenant_id=str(self.auth.tenant_id),
                            user_id=str(self.auth.user_id),
                            content=f"Connector handoff: {lane_prompt[:500]}",
                            active_form=f"Connector handoff: {lane_prompt[:500]}",
                            status="pending",
                            priority=65,
                            thread_id=str(conversation_id) if conversation_id else None,
                            metadata_json={
                                "source": "master_orchestrator",
                                "mission_id": mission_id,
                                "lane_type": lane_type,
                                "connectors": connector_names,
                            },
                            automation_json={
                                "action_type": "connector_handoff",
                                "schedule_type": "once",
                                "prompt": lane_prompt[:2000],
                                "source": "master_orchestrator",
                            },
                            is_recurring=False,
                            enabled=True,
                        )
                        synced_connectors: list[str] = []
                        connector_results: list[dict[str, Any]] = []
                        progress_events: list[dict[str, Any]] = []
                        connector_status = "completed"
                        try:
                            from sqlalchemy import select

                            from app.integrations.models.connector import Connector
                            from app.integrations.models.integration import Integration
                            from app.integrations.services.connector_orchestrator import (
                                ConnectorOrchestrator,
                            )

                            normalized_names = {
                                str(name).strip().lower()
                                for name in connector_names
                                if str(name).strip()
                            }
                            if normalized_names:
                                rows = self.db.execute(
                                    select(Connector, Integration)
                                    .join(
                                        Integration,
                                        Connector.integration_id == Integration.id,
                                    )
                                    .where(
                                        Connector.tenant_id == self.auth.tenant_id,
                                        Integration.slug.in_(sorted(normalized_names)),
                                    )
                                ).all()
                                matched_slugs = {
                                    str(integration_row.slug or "").lower()
                                    for _, integration_row in rows
                                }
                                missing_slugs = sorted(normalized_names - matched_slugs)
                                for missing_slug in missing_slugs:
                                    connector_results.append(
                                        {
                                            "integration_slug": missing_slug,
                                            "status": "not_found",
                                            "message": "No tenant connector matched this integration slug.",
                                        }
                                    )
                                    progress_events.append(
                                        {
                                            "phase": "not_found",
                                            "message": f"No tenant connector matched {missing_slug}.",
                                            "integration_slug": missing_slug,
                                        }
                                    )
                                if missing_slugs:
                                    connector_status = "failed"

                                for connector_row, integration_row in rows:
                                    integration_slug = str(
                                        integration_row.slug or connector_row.name
                                    )
                                    progress_events.append(
                                        {
                                            "phase": "start",
                                            "message": f"Starting connector sync for {integration_slug}.",
                                            "connector_id": str(connector_row.id),
                                            "integration_slug": integration_slug,
                                        }
                                    )

                                    def collect_progress(
                                        payload: dict[str, Any],
                                        *,
                                        slug: str = integration_slug,
                                    ) -> None:
                                        progress_events.append(
                                            {
                                                "integration_slug": slug,
                                                **dict(payload or {}),
                                            }
                                        )

                                    started = perf_counter()

                                    def run_connector_sync(
                                        connector_id: uuid.UUID = connector_row.id,
                                        connector_tenant_id: str = connector_row.tenant_id,
                                    ) -> dict[str, Any]:
                                        return ConnectorOrchestrator(
                                            self.db
                                        ).sync_connector(
                                            connector_id,
                                            connector_tenant_id,
                                            progress_callback=collect_progress,
                                        )

                                    connector_sync_result = await asyncio.to_thread(
                                        run_connector_sync
                                    )
                                    duration_ms = int((perf_counter() - started) * 1000)
                                    result_status = str(
                                        connector_sync_result.get("status") or "unknown"
                                    ).lower()
                                    synced_connectors.append(integration_slug)
                                    connector_results.append(
                                        {
                                            "connector_id": str(connector_row.id),
                                            "integration_slug": integration_slug,
                                            "status": result_status,
                                            "duration_ms": duration_ms,
                                            "message": connector_sync_result.get(
                                                "message"
                                            ),
                                            "health": connector_sync_result.get(
                                                "health"
                                            ),
                                            "fallback_snapshot": connector_sync_result.get(
                                                "fallback_snapshot"
                                            ),
                                        }
                                    )
                                    if result_status in {
                                        "error",
                                        "failed",
                                        "auth_expired",
                                        "offline",
                                        "not_found",
                                    }:
                                        connector_status = "failed"
                        except Exception as exc:  # noqa: BLE001
                            connector_status = "failed"
                            connector_results.append(
                                {
                                    "status": "failed",
                                    "message": str(exc),
                                    "exception_type": type(exc).__name__,
                                }
                            )
                            progress_events.append(
                                {
                                    "phase": "error",
                                    "message": str(exc),
                                    "exception_type": type(exc).__name__,
                                }
                            )
                        output = (
                            f"Connector handoff synced: {', '.join(synced_connectors)}"
                            if synced_connectors
                            else (
                                "Connector handoff failed: no matching tenant connectors found."
                                if connector_results
                                else f"Connector handoff queued: {task_id}"
                            )
                        )
                        for progress_event in progress_events[-20:]:
                            await emit(
                                "lane_observation",
                                {
                                    "mission_id": mission_id,
                                    "lane_id": lane_id,
                                    "lane_type": lane_type,
                                    "summary": str(
                                        progress_event.get("message")
                                        or progress_event.get("phase")
                                        or "Connector progress."
                                    ),
                                    "tool_name": "sync_connector",
                                    "metadata": progress_event,
                                },
                            )
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status=connector_status,
                            summary=output,
                            final_output=output,
                            metadata={
                                "connectors": connector_names,
                                "task_id": task_id,
                                "synced_connectors": synced_connectors,
                                "connector_results": connector_results,
                            },
                        )
                        await persist_lane_memory(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            summary=output,
                            output=output,
                            metadata={
                                "connectors": connector_names,
                                "task_id": task_id,
                                "connector_results": connector_results,
                            },
                        )
                        await emit(
                            "lane_result",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "status": connector_status,
                                "summary": output,
                                "output": output,
                                "task_id": task_id,
                                "metadata": {
                                    "connectors": connector_names,
                                    "synced_connectors": synced_connectors,
                                    "connector_results": connector_results,
                                },
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status=connector_status,
                            summary=output,
                            final_output=output,
                            metadata={
                                "task_id": task_id,
                                "connectors": connector_names,
                                "synced_connectors": synced_connectors,
                                "connector_results": connector_results,
                            },
                        )

                    if lane_type == "support":
                        connector_ids = [
                            str(connector_id)
                            for connector_id in (
                                lane.get("metadata", {}).get("connector_ids") or []
                            )
                            if str(connector_id).strip()
                        ]
                        support_result = await self._run_support_lane(
                            mission_id=mission_id,
                            lane=lane,
                            connector_ids=connector_ids or None,
                        )
                        output = str(
                            support_result.final_output or support_result.summary or ""
                        ).strip()
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status=support_result.status,
                            summary=support_result.summary[:1000],
                            final_output=output[:8000],
                            metadata=support_result.metadata,
                        )
                        await persist_lane_memory(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            summary=support_result.summary[:1000],
                            output=output,
                            metadata=support_result.metadata,
                        )
                        await emit(
                            "lane_result",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "status": support_result.status,
                                "summary": support_result.summary[:1000],
                                "output": output[:8000],
                                "metadata": support_result.metadata,
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status=support_result.status,
                            summary=support_result.summary[:1000],
                            final_output=output[:8000],
                            metadata=support_result.metadata,
                        )

                    if lane_type == "approval":
                        approval_data = {
                            "mission_id": mission_id,
                            "lane_id": lane_id,
                            "lane_type": lane_type,
                            "message": str(lane.get("prompt") or "Approval required."),
                            "details": lane,
                        }
                        pending_approval = True
                        pending_approval_lane_id = lane_id
                        pending_approval_lane_type = lane_type
                        blocked_lanes.add(lane_id)
                        await emit("approval_request", approval_data)
                        self.registry.request_approval(mission_id, approval_data)
                        self.registry.update_lane(
                            mission_id,
                            lane_id,
                            status="blocked",
                            metadata={"reason": "approval_required", "details": lane},
                        )
                        await emit(
                            "lane_blocked",
                            {
                                "mission_id": mission_id,
                                "lane_id": lane_id,
                                "lane_type": lane_type,
                                "reason": "approval_required",
                            },
                        )
                        return MissionLaneResult(
                            lane_id=lane_id,
                            lane_type=lane_type,
                            status="blocked",
                            summary="Awaiting approval.",
                            final_output="",
                            metadata={"details": lane},
                        )

                    output = lane_prompt[:8000]
                    self.registry.update_lane(
                        mission_id,
                        lane_id,
                        status="completed",
                        summary=output[:1000],
                        final_output=output,
                    )
                    await persist_lane_memory(
                        lane_id=lane_id,
                        lane_type=lane_type,
                        summary=output[:1000],
                        output=output,
                    )
                    await emit(
                        "lane_result",
                        {
                            "mission_id": mission_id,
                            "lane_id": lane_id,
                            "lane_type": lane_type,
                            "status": "completed",
                            "summary": output[:1000],
                            "output": output,
                        },
                    )
                    return MissionLaneResult(
                        lane_id=lane_id,
                        lane_type=lane_type,
                        status="completed",
                        summary=output[:1000],
                        final_output=output,
                        metadata={},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Orchestration lane failed: %s", lane_id)
                    self.registry.update_lane(
                        mission_id,
                        lane_id,
                        status="failed",
                        error=str(exc),
                    )
                    await emit(
                        "lane_error",
                        {
                            "mission_id": mission_id,
                            "lane_id": lane_id,
                            "lane_type": lane_type,
                            "error": str(exc),
                        },
                    )
                    return MissionLaneResult(
                        lane_id=lane_id,
                        lane_type=lane_type,
                        status="failed",
                        summary=str(exc)[:1000],
                        final_output="",
                        metadata={},
                    )

            task = asyncio.create_task(run_lane())
            lane_tasks.add(task)
            if self._lane_mutates_workspace(lane):
                active_write_lanes.add(str(lane.get("lane_id") or ""))

        async def schedule_ready_lanes() -> None:
            nonlocal pending_approval
            nonlocal pending_approval_lane_id
            nonlocal pending_approval_lane_type
            nonlocal mission_cancelled
            if control.is_cancelled():
                mission_cancelled = True
                return
            ready_lanes = [
                lane
                for lane in lane_specs.values()
                if lane.get("lane_id")
                and str(lane.get("lane_id")) not in launched_lanes
                and self._lane_dependencies_met(
                    lane,
                    completed_lanes=completed_lanes,
                    blocked_lanes=blocked_lanes,
                )
            ]
            ready_lanes.sort(key=self._lane_priority)
            for lane in ready_lanes:
                if len(lane_tasks) >= max_parallel_lanes:
                    break
                lane_type = str(lane.get("lane_type") or "")
                lane_id = str(lane.get("lane_id") or "")
                mutates_workspace = self._lane_mutates_workspace(lane)
                if active_write_lanes or (mutates_workspace and lane_tasks):
                    continue
                if lane_type == "approval":
                    approval_data = {
                        "mission_id": mission_id,
                        "lane_id": lane_id,
                        "lane_type": lane_type,
                        "message": str(lane.get("prompt") or "Approval required."),
                        "details": lane,
                    }
                    pending_approval = True
                    pending_approval_lane_id = lane_id
                    pending_approval_lane_type = lane_type
                    blocked_lanes.add(lane_id)
                    self.registry.request_approval(mission_id, approval_data)
                    self.registry.update_lane(
                        mission_id,
                        lane_id,
                        status="blocked",
                        metadata={"reason": "approval_required", "details": lane},
                    )
                    await emit("approval_request", approval_data)
                    await emit(
                        "lane_blocked",
                        {
                            "mission_id": mission_id,
                            "lane_id": lane_id,
                            "lane_type": lane_type,
                            "reason": "approval_required",
                        },
                    )
                    launched_lanes.add(lane_id)
                    continue
                await launch_lane(lane)

        while True:
            if control.is_cancelled():
                mission_cancelled = True
                break
            await schedule_ready_lanes()

            while not event_queue.empty():
                yield await event_queue.get()

            if lane_tasks:
                done, pending = await asyncio.wait(
                    lane_tasks,
                    timeout=0.08,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                lane_tasks = set(pending)
                for task in done:
                    result = await task
                    active_write_lanes.discard(result.lane_id)
                    lane_results[result.lane_id] = result
                    completed_lanes.add(result.lane_id)
                    self.registry.append_lane_result(
                        mission_id,
                        {
                            "lane_id": result.lane_id,
                            "lane_type": result.lane_type,
                            "status": result.status,
                            "summary": result.summary,
                            "final_output": result.final_output,
                            "metadata": result.metadata,
                        },
                    )
                while not event_queue.empty():
                    yield await event_queue.get()
                if control.is_cancelled():
                    mission_cancelled = True
                    break
                continue

            if any(
                lane_id not in launched_lanes
                and not self._lane_dependencies_met(
                    lane,
                    completed_lanes=completed_lanes,
                    blocked_lanes=blocked_lanes,
                )
                for lane_id, lane in lane_specs.items()
            ):
                if pending_approval and pending_approval_lane_type == "approval":
                    if not await_approval:
                        break
                    while True:
                        current_mission = self.registry.get_mission(mission_id) or {}
                        current_status = str(
                            current_mission.get("status") or ""
                        ).lower()
                        approval_queue = list(
                            current_mission.get("approval_queue") or []
                        )
                        if current_status == "declined":
                            pending_approval = False
                            approval_declined = True
                            break
                        if current_status == "running" and not approval_queue:
                            pending_approval = False
                            if pending_approval_lane_id:
                                blocked_lanes.discard(pending_approval_lane_id)
                                lane_state = lane_specs.get(pending_approval_lane_id)
                                if lane_state is not None:
                                    lane_state["status"] = "approved"
                            break
                        await asyncio.sleep(0.2)
                    if approval_declined:
                        break
                    if pending_approval:
                        break
                    continue
                if pending_approval:
                    break
                await asyncio.sleep(0.05)
                continue

            break

        while not event_queue.empty():
            yield await event_queue.get()

        if mission_cancelled:
            cancelled_text = "Mission cancelled."
            duration_ms = int((perf_counter() - start_time) * 1000)
            self.registry.touch_mission(
                mission_id,
                status="cancelled",
                last_event_type="mission_cancelled",
                last_event_message="Mission cancelled by user.",
                runtime_state=self._runtime_visibility_state(
                    conversation_id=conversation_id,
                    plan=plan,
                    runtime_diagnostics=mission_runtime_diagnostics,
                ),
            )
            self.registry.complete_mission(
                mission_id=mission_id,
                status="cancelled",
                summary=cancelled_text,
                final_output=cancelled_text,
                duration_ms=duration_ms,
            )
            yield StreamEvent(
                event="mission_summary",
                data={
                    "mission_id": mission_id,
                    "summary": cancelled_text,
                    "lane_count": len(lane_results),
                    "duration_ms": duration_ms,
                    "status": "cancelled",
                    "execution_mode": normalized_execution_mode,
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id,
                        plan=plan,
                        runtime_diagnostics=mission_runtime_diagnostics,
                    ),
                },
            )
            yield StreamEvent(
                event="mission_done",
                data={
                    "mission_id": mission_id,
                    "status": "cancelled",
                    "summary": cancelled_text,
                    "duration_ms": duration_ms,
                    "execution_mode": normalized_execution_mode,
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id,
                        plan=plan,
                        runtime_diagnostics=mission_runtime_diagnostics,
                    ),
                },
            )
            return

        self.registry.touch_mission(
            mission_id,
            status=(
                "awaiting_approval"
                if pending_approval
                else "declined" if approval_declined else "synthesizing"
            ),
            last_event_type="lane_complete",
            last_event_message="Parallel lanes complete.",
            runtime_state=self._runtime_visibility_state(
                conversation_id=conversation_id,
                plan=plan,
                runtime_diagnostics=mission_runtime_diagnostics,
            ),
        )

        if approval_declined:
            decline_text = "Mission declined."
            duration_ms = int((perf_counter() - start_time) * 1000)
            self.registry.complete_mission(
                mission_id=mission_id,
                status="declined",
                summary=decline_text,
                final_output="",
                duration_ms=duration_ms,
            )
            yield StreamEvent(
                event="mission_summary",
                data={
                    "mission_id": mission_id,
                    "summary": decline_text,
                    "lane_count": len(lane_results),
                    "duration_ms": duration_ms,
                    "status": "declined",
                    "execution_mode": normalized_execution_mode,
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id,
                        plan=plan,
                        runtime_diagnostics=mission_runtime_diagnostics,
                    ),
                },
            )
            yield StreamEvent(
                event="mission_done",
                data={
                    "mission_id": mission_id,
                    "status": "declined",
                    "summary": decline_text,
                    "duration_ms": duration_ms,
                    "execution_mode": normalized_execution_mode,
                    "runtime_state": self._runtime_visibility_state(
                        conversation_id=conversation_id,
                        plan=plan,
                        runtime_diagnostics=mission_runtime_diagnostics,
                    ),
                },
            )
            return

        lane_result_list = list(lane_results.values())
        main_lane_result = lane_results.get("main_chat")
        main_answer = main_lane_result.final_output if main_lane_result else ""
        synthesized = await self._synthesize_mission_output(
            objective=objective,
            plan=plan,
            main_answer=main_answer,
            lane_results=lane_result_list,
            note_content=note_content,
        )
        summary_text = (
            synthesized or main_answer or self._combine_lane_outputs(lane_result_list)
        )
        duration_ms = int((perf_counter() - start_time) * 1000)
        lane_statuses = {str(result.status) for result in lane_result_list}
        if pending_approval:
            final_status = "awaiting_approval"
        elif "failed" in lane_statuses:
            final_status = "failed"
        elif "blocked" in lane_statuses:
            final_status = "blocked"
        elif "cancelled" in lane_statuses:
            final_status = "cancelled"
        else:
            final_status = "completed"
        self.registry.complete_mission(
            mission_id=mission_id,
            status=final_status,
            summary=summary_text[:4000],
            final_output=summary_text[:8000],
            duration_ms=duration_ms,
        )

        if final_status in {"blocked", "failed"} and full_autonomy:
            try:
                if self.registry.schedule_continuation(mission_id):
                    from app.worker.tasks_deepspace import continue_full_autonomy_mission

                    continue_full_autonomy_mission.apply_async(
                        args=[mission_id], countdown=5
                    )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to schedule full-autonomy continuation")

        yield StreamEvent(
            event="mission_summary",
            data={
                "mission_id": mission_id,
                "summary": summary_text,
                "lane_count": len(lane_result_list),
                "duration_ms": duration_ms,
                "status": final_status,
                "execution_mode": normalized_execution_mode,
                "planner_source": plan.get("planner_source"),
                "runtime_state": self._runtime_visibility_state(
                    conversation_id=conversation_id,
                    plan=plan,
                    runtime_diagnostics=mission_runtime_diagnostics,
                ),
            },
        )
        yield StreamEvent(
            event="mission_done",
            data={
                "mission_id": mission_id,
                "status": final_status,
                "summary": summary_text,
                "duration_ms": duration_ms,
                "execution_mode": normalized_execution_mode,
                "planner_source": plan.get("planner_source"),
                "runtime_state": self._runtime_visibility_state(
                    conversation_id=conversation_id,
                    plan=plan,
                    runtime_diagnostics=mission_runtime_diagnostics,
                ),
            },
        )

    async def execute_mission(
        self,
        *,
        objective: str,
        note_content: str | None = None,
        previous_messages: list[dict[str, Any]] | None = None,
        conversation_id: uuid.UUID | None = None,
        execution_mode: str = "auto_review",
        await_approval: bool = False,
    ) -> dict[str, Any]:
        mission_id: str | None = None
        async for event in self.stream_mission(
            objective=objective,
            note_content=note_content,
            previous_messages=previous_messages,
            conversation_id=conversation_id,
            execution_mode=execution_mode,
            await_approval=await_approval,
        ):
            if event.event == "mission_start":
                mission_id = str(event.data.get("mission_id") or "") or mission_id
        if mission_id:
            mission = self.registry.get_mission(mission_id)
            if mission:
                return mission
        return {}

    async def execute_support_mission(
        self,
        *,
        include_vitals: bool = True,
        include_daemon: bool = True,
        include_connectors: bool = True,
        connector_ids: list[str] | None = None,
        execution_mode: str = "auto_review",
    ) -> dict[str, Any]:
        mission_id = str(uuid.uuid4())
        normalized_execution_mode = (
            "full_access"
            if str(execution_mode).strip().lower() == "full_access"
            else "auto_review"
        )
        support_lanes: list[dict[str, Any]] = []
        if include_vitals:
            support_lanes.append(
                {
                    "lane_id": "support_vitals",
                    "lane_type": "support",
                    "title": "System Vitals Check",
                    "prompt": "Check system vitals, runtime health, and daemon readiness for the mission environment.",
                    "priority": 96,
                    "depends_on": [],
                    "blocked_by": [],
                    "subagent_type": "support",
                    "metadata": {"role": "support", "support_kind": "vitals"},
                    "status": "pending",
                }
            )
        if include_daemon:
            support_lanes.append(
                {
                    "lane_id": "support_daemon",
                    "lane_type": "support",
                    "title": "Daemon Heartbeat Check",
                    "prompt": "Check the proactive daemon heartbeat and monitoring pulse for the environment.",
                    "priority": 94,
                    "depends_on": [],
                    "blocked_by": [],
                    "subagent_type": "support",
                    "metadata": {"role": "support", "support_kind": "daemon_heartbeat"},
                    "status": "pending",
                }
            )
        if include_connectors:
            support_lanes.append(
                {
                    "lane_id": "support_connectors",
                    "lane_type": "support",
                    "title": "Connector Health Sweep",
                    "prompt": "Validate connector health and live provider connectivity across the workspace.",
                    "priority": 92,
                    "depends_on": [],
                    "blocked_by": [],
                    "subagent_type": "support",
                    "metadata": {
                        "role": "support",
                        "support_kind": "connector_health",
                        "connector_ids": [
                            str(connector_id)
                            for connector_id in connector_ids or []
                            if str(connector_id).strip()
                        ],
                    },
                    "status": "pending",
                }
            )

        graph_nodes: list[dict[str, Any]] = []
        graph_edges: list[dict[str, Any]] = []
        for index, lane in enumerate(support_lanes):
            graph_nodes.append(
                {
                    "id": lane["lane_id"],
                    "label": lane["title"],
                    "kind": lane["lane_type"],
                    "world": "systems",
                    "x": (index % 3) * 240 - 120,
                    "y": (index // 3) * 180 - 120,
                    "z": 100 + index * 8,
                    "status": lane["status"],
                    "tone": "amber",
                    "meta": {
                        "support_kind": lane.get("metadata", {}).get("support_kind"),
                        "role": lane.get("metadata", {}).get("role"),
                        "connector_ids": lane.get("metadata", {}).get("connector_ids")
                        or [],
                    },
                }
            )
            graph_edges.append(
                {
                    "source": "support_router",
                    "target": lane["lane_id"],
                    "label": "probe",
                    "tone": "amber",
                    "kind": "support",
                }
            )

        plan = {
            "planner_source": "system_support",
            "planner_version": 1,
            "objective": "System support sweep",
            "note_content": "vitals, daemon heartbeat, connector health",
            "execution_mode": normalized_execution_mode,
            "summary": "System support sweep for vitals, daemon heartbeat, and connector health.",
            "signals": {
                "support": True,
                "vitals": include_vitals,
                "daemon": include_daemon,
                "connector": include_connectors,
            },
            "parallel_limit": max(1, len(support_lanes)),
            "approval_queue": [],
            "lanes": support_lanes,
            "graph": {
                "nodes": [
                    {
                        "id": "support_router",
                        "label": "Support Router",
                        "kind": "core",
                        "world": "systems",
                        "x": 0.0,
                        "y": -260.0,
                        "z": 140.0,
                        "status": "active",
                        "tone": "amber",
                        "meta": {
                            "support": True,
                            "execution_mode": normalized_execution_mode,
                        },
                    },
                    *graph_nodes,
                ],
                "edges": graph_edges,
                "worlds": [
                    {
                        "id": "systems",
                        "label": "System Mesh",
                        "description": "Vitals, daemon heartbeat, and connector health support checks.",
                    }
                ],
            },
            "safety": {
                "gated_actions_detected": False,
                "lane_count": len(support_lanes),
                "parallel_lane_count": len(support_lanes),
                "dynamic_fanout": 0,
            },
        }

        start_time = perf_counter()
        self.registry.register_mission(
            mission_id=mission_id,
            tenant_id=str(self.auth.tenant_id),
            user_id=str(self.auth.user_id),
            objective="System support sweep",
            plan=plan,
            parent_id=None,
            status="planning",
            execution_mode=normalized_execution_mode,
        )
        self.registry.touch_mission(
            mission_id,
            status="running",
            last_event_type="support_start",
            last_event_message="Support sweep started.",
        )

        daemon_healthy = not include_daemon
        vitals: dict[str, Any] = {}
        connector_health: dict[str, Any] = {}

        async def run_support_lane(lane: dict[str, Any]) -> MissionLaneResult:
            lane_id = str(lane.get("lane_id") or "")
            support_kind = (
                str(lane.get("metadata", {}).get("support_kind") or "").strip().lower()
            )
            self.registry.update_lane(mission_id, lane_id, status="running")
            try:
                if support_kind == "vitals":
                    current_vitals = await VitalsService.get_system_vitals(
                        self.auth.tenant_id
                    )
                    current_output = json.dumps(current_vitals, ensure_ascii=False)
                    self.db.add(
                        AgentActivity(
                            tenant_id=self.auth.tenant_id,
                            activity_type="heartbeat",
                            description="System vitals checked.",
                            source="support",
                            metadata_json={
                                "phase": "vitals",
                                "mission_id": mission_id,
                                "vitals": current_vitals,
                            },
                        )
                    )
                    return MissionLaneResult(
                        lane_id=lane_id,
                        lane_type="support",
                        status="completed",
                        summary="System vitals checked.",
                        final_output=current_output,
                        metadata={"vitals": current_vitals},
                    )
                if support_kind == "daemon_heartbeat":
                    from app.services.deepspace.subagents.subagent_registry import (
                        SubagentRegistry,
                    )

                    daemon_registry = SubagentRegistry(self.settings)
                    heartbeat = daemon_registry.get_daemon_heartbeat() or {}
                    timestamp_raw = str(heartbeat.get("timestamp") or "")
                    healthy = False
                    if timestamp_raw:
                        try:
                            timestamp = datetime.fromisoformat(
                                timestamp_raw.replace("Z", "+00:00")
                            )
                            interval_raw = heartbeat.get("interval_seconds") or getattr(
                                self.settings,
                                "deepspace_proactive_daemon_interval_seconds",
                                300,
                            )
                            interval_seconds = int(
                                interval_raw if interval_raw is not None else 300
                            )
                            healthy = heartbeat.get("phase") != "error" and (
                                datetime.now(UTC) - timestamp
                            ).total_seconds() <= max(interval_seconds * 3, 300)
                        except Exception:  # noqa: BLE001
                            healthy = False
                    current_output = json.dumps(
                        {"heartbeat": heartbeat, "healthy": healthy},
                        ensure_ascii=False,
                    )
                    self.db.add(
                        AgentActivity(
                            tenant_id=self.auth.tenant_id,
                            activity_type="heartbeat",
                            description="Daemon heartbeat checked.",
                            source="support",
                            metadata_json={
                                "phase": "daemon",
                                "mission_id": mission_id,
                                "daemon_heartbeat": heartbeat,
                                "healthy": healthy,
                            },
                        )
                    )
                    return MissionLaneResult(
                        lane_id=lane_id,
                        lane_type="support",
                        status="completed" if healthy else "degraded",
                        summary="Daemon heartbeat checked.",
                        final_output=current_output,
                        metadata={"daemon_heartbeat": heartbeat, "healthy": healthy},
                    )
                if support_kind == "connector_health":
                    rows = self.db.execute(
                        select(Connector, Integration)
                        .join(Integration, Connector.integration_id == Integration.id)
                        .where(
                            Connector.tenant_id == self.auth.tenant_id,
                            Connector.status != ConnectorStatus.SYNCING,
                        )
                    ).all()
                    if connector_ids:
                        wanted_ids = {
                            str(connector_id).strip()
                            for connector_id in connector_ids
                            if str(connector_id).strip()
                        }
                        rows = [row for row in rows if str(row[0].id) in wanted_ids]

                    from app.integrations.services.connector_orchestrator import (
                        ConnectorOrchestrator,
                    )

                    health_map: dict[str, Any] = {}
                    healthy = True
                    for connector_row, integration_row in rows:
                        report = ConnectorOrchestrator(
                            self.db
                        ).validate_connector_health(
                            connector_row.id,
                            connector_row.tenant_id,
                        )
                        normalized_report = {
                            "status": str(report.get("status") or "degraded"),
                            "healthy": bool(report.get("healthy")),
                            "message": report.get("message")
                            or report.get("error_message")
                            or report.get("last_error_message"),
                            "health": report.get("health"),
                            "integration_slug": integration_row.slug,
                            "connector_name": connector_row.name,
                            "connector_id": str(connector_row.id),
                        }
                        health_map[str(connector_row.id)] = normalized_report
                        if normalized_report["healthy"]:
                            self.db.add(
                                AgentActivity(
                                    tenant_id=self.auth.tenant_id,
                                    activity_type="heartbeat",
                                    description=f"Connector health validated for {connector_row.name}.",
                                    source=integration_row.slug or "connector",
                                    metadata_json={
                                        "phase": "connector_health",
                                        "mission_id": mission_id,
                                        "connector_id": str(connector_row.id),
                                        "connector_name": connector_row.name,
                                        "integration_slug": integration_row.slug,
                                        "health": report,
                                    },
                                )
                            )
                        else:
                            healthy = False
                            self.db.add(
                                AgentActivity(
                                    tenant_id=self.auth.tenant_id,
                                    activity_type="error",
                                    description=f"Connector health validation failed for {connector_row.name}.",
                                    source=integration_row.slug or "connector",
                                    metadata_json={
                                        "phase": "connector_health",
                                        "mission_id": mission_id,
                                        "connector_id": str(connector_row.id),
                                        "connector_name": connector_row.name,
                                        "integration_slug": integration_row.slug,
                                        "health": report,
                                    },
                                )
                            )
                            self.todo_service.upsert_task(
                                tenant_id=str(self.auth.tenant_id),
                                user_id=str(self.auth.user_id),
                                content=f"Repair connector health for {connector_row.name}",
                                active_form=f"Repair connector health for {connector_row.name}",
                                status="pending",
                                priority=80,
                                metadata_json={
                                    "source": "support",
                                    "mission_id": mission_id,
                                    "connector_id": str(connector_row.id),
                                    "integration_slug": integration_row.slug,
                                    "phase": "connector_health",
                                    "health": report,
                                },
                            )

                    current_output = json.dumps(
                        {"healthy": healthy, "connector_health": health_map},
                        ensure_ascii=False,
                    )
                    return MissionLaneResult(
                        lane_id=lane_id,
                        lane_type="support",
                        status="completed" if healthy else "degraded",
                        summary="Connector health sweep completed.",
                        final_output=current_output,
                        metadata={"connector_health": health_map, "healthy": healthy},
                    )

                return MissionLaneResult(
                    lane_id=lane_id,
                    lane_type="support",
                    status="completed",
                    summary="Support lane completed.",
                    final_output="",
                    metadata={},
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Support lane failed: %s", lane_id)
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    logger.debug("Support lane rollback failed.", exc_info=True)
                return MissionLaneResult(
                    lane_id=lane_id,
                    lane_type="support",
                    status="failed",
                    summary=str(exc)[:1000],
                    final_output="",
                    metadata={"error": str(exc)},
                )

        lane_results: list[MissionLaneResult] = []
        for lane in support_lanes:
            result = await run_support_lane(lane)
            lane_results.append(result)
            self.registry.update_lane(
                mission_id,
                result.lane_id,
                status=result.status,
                summary=result.summary[:1000],
                final_output=result.final_output[:8000],
                metadata=result.metadata,
            )
            self.registry.append_lane_result(
                mission_id,
                {
                    "lane_id": result.lane_id,
                    "lane_type": result.lane_type,
                    "status": result.status,
                    "summary": result.summary,
                    "final_output": result.final_output,
                    "metadata": result.metadata,
                },
            )
            try:
                self.db.commit()
            except Exception:  # noqa: BLE001
                self.db.rollback()
                logger.debug("Failed to commit support lane updates.", exc_info=True)

        vitals_result = next(
            (result for result in lane_results if result.metadata.get("vitals")), None
        )
        daemon_result = next(
            (
                result
                for result in lane_results
                if "daemon_heartbeat" in result.metadata
            ),
            None,
        )
        connector_result = next(
            (
                result
                for result in lane_results
                if "connector_health" in result.metadata
            ),
            None,
        )
        if vitals_result and isinstance(vitals_result.metadata.get("vitals"), dict):
            vitals = cast(dict[str, Any], vitals_result.metadata.get("vitals"))
        if daemon_result:
            daemon_healthy = bool(daemon_result.metadata.get("healthy"))
        if connector_result and isinstance(
            connector_result.metadata.get("connector_health"), dict
        ):
            connector_health = cast(
                dict[str, Any], connector_result.metadata.get("connector_health")
            )

        vitals_ok = bool(
            not include_vitals
            or (
                vitals
                and str(vitals.get("internet") or "") == "connected"
                and str(vitals.get("llm") or "") == "connected"
            )
        )
        connector_ok = bool(
            not include_connectors
            or (
                connector_result is not None
                and connector_result.status != "failed"
                and all(bool(item.get("healthy")) for item in connector_health.values())
            )
        )
        healthy = bool(vitals_ok and daemon_healthy and connector_ok)
        summary = (
            "Support sweep healthy."
            if healthy
            else "Support sweep detected degraded infrastructure."
        )
        duration_ms = int((perf_counter() - start_time) * 1000)
        self.registry.complete_mission(
            mission_id=mission_id,
            status="completed" if healthy else "degraded",
            summary=summary,
            final_output=json.dumps(
                {
                    "healthy": healthy,
                    "vitals": vitals,
                    "daemon_heartbeat": (
                        daemon_result.metadata.get("daemon_heartbeat")
                        if daemon_result
                        else {}
                    ),
                    "connector_health": connector_health,
                },
                ensure_ascii=False,
            ),
            duration_ms=duration_ms,
        )
        try:
            self.db.commit()
        except Exception:  # noqa: BLE001
            self.db.rollback()
            logger.debug("Failed to commit support mission completion.", exc_info=True)
        support_report = self.registry.get_mission(mission_id) or {}
        support_report.update(
            {
                "healthy": healthy,
                "vitals": vitals,
                "daemon_heartbeat": (
                    daemon_result.metadata.get("daemon_heartbeat")
                    if daemon_result
                    else {}
                ),
                "connector_health": connector_health,
            }
        )
        return support_report

    async def _run_support_lane(
        self,
        *,
        mission_id: str,
        lane: dict[str, Any],
        connector_ids: list[str] | None = None,
    ) -> MissionLaneResult:
        lane_id = str(lane.get("lane_id") or "")
        support_kind = (
            str(lane.get("metadata", {}).get("support_kind") or "").strip().lower()
        )
        try:
            if support_kind == "vitals":
                current_vitals = await VitalsService.get_system_vitals(
                    self.auth.tenant_id
                )
                current_output = json.dumps(current_vitals, ensure_ascii=False)
                self.db.add(
                    AgentActivity(
                        tenant_id=self.auth.tenant_id,
                        activity_type="heartbeat",
                        description="System vitals checked.",
                        source="support",
                        metadata_json={
                            "phase": "vitals",
                            "mission_id": mission_id,
                            "vitals": current_vitals,
                        },
                    )
                )
                try:
                    self.db.commit()
                except Exception:  # noqa: BLE001
                    self.db.rollback()
                    logger.debug(
                        "Failed to commit support vitals activity.", exc_info=True
                    )
                return MissionLaneResult(
                    lane_id=lane_id,
                    lane_type="support",
                    status="completed",
                    summary="System vitals checked.",
                    final_output=current_output,
                    metadata={"vitals": current_vitals},
                )

            if support_kind == "daemon_heartbeat":
                from app.services.deepspace.subagents.subagent_registry import SubagentRegistry

                daemon_registry = SubagentRegistry(self.settings)
                heartbeat = daemon_registry.get_daemon_heartbeat() or {}
                timestamp_raw = str(heartbeat.get("timestamp") or "")
                healthy = False
                if timestamp_raw:
                    try:
                        timestamp = datetime.fromisoformat(
                            timestamp_raw.replace("Z", "+00:00")
                        )
                        interval_raw = heartbeat.get("interval_seconds") or getattr(
                            self.settings,
                            "deepspace_proactive_daemon_interval_seconds",
                            300,
                        )
                        interval_seconds = int(
                            interval_raw if interval_raw is not None else 300
                        )
                        healthy = heartbeat.get("phase") != "error" and (
                            datetime.now(UTC) - timestamp
                        ).total_seconds() <= max(interval_seconds * 3, 300)
                    except Exception:  # noqa: BLE001
                        healthy = False
                current_output = json.dumps(
                    {"heartbeat": heartbeat, "healthy": healthy},
                    ensure_ascii=False,
                )
                self.db.add(
                    AgentActivity(
                        tenant_id=self.auth.tenant_id,
                        activity_type="heartbeat",
                        description="Daemon heartbeat checked.",
                        source="support",
                        metadata_json={
                            "phase": "daemon",
                            "mission_id": mission_id,
                            "daemon_heartbeat": heartbeat,
                            "healthy": healthy,
                        },
                    )
                )
                try:
                    self.db.commit()
                except Exception:  # noqa: BLE001
                    self.db.rollback()
                    logger.debug(
                        "Failed to commit daemon support activity.", exc_info=True
                    )
                return MissionLaneResult(
                    lane_id=lane_id,
                    lane_type="support",
                    status="completed" if healthy else "degraded",
                    summary="Daemon heartbeat checked.",
                    final_output=current_output,
                    metadata={"daemon_heartbeat": heartbeat, "healthy": healthy},
                )

            if support_kind == "connector_health":
                rows = self.db.execute(
                    select(Connector, Integration)
                    .join(Integration, Connector.integration_id == Integration.id)
                    .where(
                        Connector.tenant_id == self.auth.tenant_id,
                        Connector.status != ConnectorStatus.SYNCING,
                    )
                ).all()
                if connector_ids:
                    wanted_ids = {
                        str(connector_id).strip()
                        for connector_id in connector_ids
                        if str(connector_id).strip()
                    }
                    rows = [row for row in rows if str(row[0].id) in wanted_ids]

                from app.integrations.services.connector_orchestrator import (
                    ConnectorOrchestrator,
                )

                health_map: dict[str, Any] = {}
                healthy = True
                for connector_row, integration_row in rows:
                    report = ConnectorOrchestrator(self.db).validate_connector_health(
                        connector_row.id,
                        connector_row.tenant_id,
                    )
                    normalized_report = {
                        "status": str(report.get("status") or "degraded"),
                        "healthy": bool(report.get("healthy")),
                        "message": report.get("message")
                        or report.get("error_message")
                        or report.get("last_error_message"),
                        "health": report.get("health"),
                        "integration_slug": integration_row.slug,
                        "connector_name": connector_row.name,
                        "connector_id": str(connector_row.id),
                    }
                    health_map[str(connector_row.id)] = normalized_report
                    if normalized_report["healthy"]:
                        self.db.add(
                            AgentActivity(
                                tenant_id=self.auth.tenant_id,
                                activity_type="heartbeat",
                                description=f"Connector health validated for {connector_row.name}.",
                                source=integration_row.slug or "connector",
                                metadata_json={
                                    "phase": "connector_health",
                                    "mission_id": mission_id,
                                    "connector_id": str(connector_row.id),
                                    "connector_name": connector_row.name,
                                    "integration_slug": integration_row.slug,
                                    "health": report,
                                },
                            )
                        )
                    else:
                        healthy = False
                        self.db.add(
                            AgentActivity(
                                tenant_id=self.auth.tenant_id,
                                activity_type="error",
                                description=f"Connector health validation failed for {connector_row.name}.",
                                source=integration_row.slug or "connector",
                                metadata_json={
                                    "phase": "connector_health",
                                    "mission_id": mission_id,
                                    "connector_id": str(connector_row.id),
                                    "connector_name": connector_row.name,
                                    "integration_slug": integration_row.slug,
                                    "health": report,
                                },
                            )
                        )
                        self.todo_service.upsert_task(
                            tenant_id=str(self.auth.tenant_id),
                            user_id=str(self.auth.user_id),
                            content=f"Repair connector health for {connector_row.name}",
                            active_form=f"Repair connector health for {connector_row.name}",
                            status="pending",
                            priority=80,
                            metadata_json={
                                "source": "support",
                                "mission_id": mission_id,
                                "connector_id": str(connector_row.id),
                                "integration_slug": integration_row.slug,
                                "phase": "connector_health",
                                "health": report,
                            },
                        )

                current_output = json.dumps(
                    {"healthy": healthy, "connector_health": health_map},
                    ensure_ascii=False,
                )
                try:
                    self.db.commit()
                except Exception:  # noqa: BLE001
                    self.db.rollback()
                    logger.debug(
                        "Failed to commit connector support updates.", exc_info=True
                    )
                return MissionLaneResult(
                    lane_id=lane_id,
                    lane_type="support",
                    status="completed" if healthy else "degraded",
                    summary="Connector health sweep completed.",
                    final_output=current_output,
                    metadata={"connector_health": health_map, "healthy": healthy},
                )

            return MissionLaneResult(
                lane_id=lane_id,
                lane_type="support",
                status="completed",
                summary="Support lane completed.",
                final_output="",
                metadata={},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Support lane failed: %s", lane_id)
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                logger.debug("Support lane rollback failed.", exc_info=True)
            return MissionLaneResult(
                lane_id=lane_id,
                lane_type="support",
                status="failed",
                summary=str(exc)[:1000],
                final_output="",
                metadata={"error": str(exc)},
            )

    def _build_plan(
        self,
        *,
        objective: str,
        note_content: str | None = None,
        execution_mode: str = "auto_review",
    ) -> dict[str, Any]:
        text = f"{objective}\n{note_content or ''}".lower()
        tokens = set(re.findall(r"[a-z0-9_+-]+", text))
        lanes: list[dict[str, Any]] = []
        approval_queue: list[dict[str, Any]] = []

        research_terms = {
            "research",
            "investigate",
            "explore",
            "compare",
            "verify",
            "find",
        }
        analysis_terms = {
            "analyze",
            "analysis",
            "diagnose",
            "compute",
            "calculate",
            "math",
            "physics",
            "data",
            "architecture",
            "workflow",
            "optimize",
        }
        writer_terms = {
            "write",
            "draft",
            "compose",
            "summarize",
            "document",
            "report",
            "proposal",
        }
        executor_terms = {
            "implement",
            "fix",
            "patch",
            "refactor",
            "build",
            "code",
            "change",
            "update",
            "deploy",
        }
        memory_terms = {"remember", "store", "persist", "save", "learn", "note", "log"}
        proactive_terms = {
            "daily",
            "weekly",
            "recurring",
            "monitor",
            "proactive",
            "schedule",
            "remind",
        }
        approval_terms = {
            "delete",
            "remove",
            "destroy",
            "purge",
            "wipe",
            "terminate",
            "drop",
            "erase",
        }
        connector_terms = {
            "email",
            "gmail",
            "calendar",
            "slack",
            "notion",
            "github",
            "drive",
            "connector",
            "sync",
        }

        def has_any(keywords: set[str]) -> bool:
            return bool(tokens.intersection(keywords))

        def status_tone(value: str) -> str:
            normalized = value.lower()
            if normalized in {"running", "active", "connected", "available", "healthy"}:
                return "emerald"
            if normalized in {"pending", "paused", "waiting", "scheduled"}:
                return "amber"
            if normalized in {"error", "failed", "degraded", "stale", "terminating"}:
                return "rose"
            return "slate"

        suppress_proactive = False
        normalized_obj = objective.lower()
        if (
            "create proactive follow-up work" in normalized_obj
            or "restore proactive capacity" in normalized_obj
            or "investigate gmail proactive message failure" in normalized_obj
            or "investigate gmail proactive scan failure" in normalized_obj
        ):
            suppress_proactive = True

        signals = {
            "research": has_any(research_terms),
            "analysis": has_any(analysis_terms),
            "writer": has_any(writer_terms),
            "executor": has_any(executor_terms),
            "memory": has_any(memory_terms),
            "proactive": has_any(proactive_terms) and not suppress_proactive,
            "approval": has_any(approval_terms),
            "connector": has_any(connector_terms),
        }

        def add_lane(
            lane_type: str,
            prompt: str,
            *,
            title: str,
            metadata: dict[str, Any] | None = None,
            depends_on: list[str] | None = None,
            blocked_by: list[str] | None = None,
            priority: int = 50,
            subagent_type: str | None = None,
        ) -> str:
            lane_id = f"{lane_type}_{len(lanes) + 1}"
            lane = {
                "lane_id": lane_id,
                "lane_type": lane_type,
                "title": title,
                "prompt": prompt,
                "parallelizable": lane_type != "approval",
                "requires_approval": lane_type == "approval",
                "depends_on": depends_on or [],
                "blocked_by": blocked_by or [],
                "priority": priority,
                "subagent_type": subagent_type or lane_type,
                "metadata": metadata or {},
                "status": "pending",
            }
            lanes.append(lane)
            return lane_id

        main_chat_id = add_lane(
            "main_chat",
            objective,
            title="AverQel Mission Core",
            metadata={
                "role": "primary",
                "signal_profile": signals,
            },
            priority=100,
        )

        research_ids: list[str] = []
        if signals["research"]:
            research_ids.append(
                add_lane(
                    "research",
                    f"Research and verify the mission objective with primary evidence: {objective}",
                    title="Research Evidence Swarm",
                    metadata={"role": "evidence"},
                    priority=90,
                )
            )
            if "compare" in tokens or "verify" in tokens or len(tokens) > 18:
                research_ids.append(
                    add_lane(
                        "research",
                        f"Research counterpoints, risks, and alternative interpretations for: {objective}",
                        title="Research Counterpoints Swarm",
                        metadata={"role": "counterpoints"},
                        priority=88,
                    )
                )
            if note_content:
                research_ids.append(
                    add_lane(
                        "research",
                        f"Research the workspace note context and reconcile it with the objective: {objective}",
                        title="Research Context Swarm",
                        metadata={"role": "context"},
                        priority=86,
                    )
                )

        analysis_ids: list[str] = []
        if signals["analysis"] or research_ids:
            analysis_dependencies = research_ids or [main_chat_id]
            analysis_ids.append(
                add_lane(
                    "analysis",
                    f"Analyze and structure the mission result from the available evidence: {objective}",
                    title="Analysis Core Swarm",
                    metadata={"role": "core"},
                    depends_on=analysis_dependencies,
                    priority=80,
                    subagent_type="analyzer",
                )
            )
            if (
                signals["executor"]
                or signals["writer"]
                or "risk" in tokens
                or "tradeoff" in tokens
            ):
                analysis_ids.append(
                    add_lane(
                        "analysis",
                        f"Analyze failure modes, constraints, and validation risks for: {objective}",
                        title="Analysis Risk Swarm",
                        metadata={"role": "risk"},
                        depends_on=analysis_dependencies,
                        priority=78,
                        subagent_type="analyzer",
                    )
                )

        if signals["writer"]:
            writer_dependencies = analysis_ids or research_ids or [main_chat_id]
            add_lane(
                "writer",
                f"Draft a crisp final deliverable for: {objective}",
                title="Writer Swarm",
                metadata={"role": "writer"},
                depends_on=writer_dependencies,
                priority=70,
                subagent_type="writer",
            )

        executor_blockers: list[str] = []
        approval_id: str | None = None
        if signals["approval"] and execution_mode != "full_access":
            approval_id = add_lane(
                "approval",
                "Approval required before gated work continues.",
                title="Approval Gate",
                metadata={"reason": "gated action detected"},
                priority=120,
            )
            approval_queue.append(
                {
                    "lane_id": approval_id,
                    "lane_type": "approval",
                    "message": "This mission includes a gated or destructive action that must be approved.",
                }
            )
            executor_blockers.append(approval_id)

        if signals["executor"]:
            executor_dependencies = analysis_ids or research_ids or [main_chat_id]
            add_lane(
                "executor",
                f"Execute the implementation steps or operational changes for: {objective}",
                title="Executor Swarm",
                metadata={"role": "executor"},
                depends_on=executor_dependencies,
                blocked_by=executor_blockers,
                priority=72,
                subagent_type="executor",
            )

        if signals["memory"]:
            memory_dependencies = analysis_ids or [main_chat_id]
            add_lane(
                "memory",
                f"Store mission memory and handoff notes for: {objective}",
                title="Memory Handoff",
                metadata={"role": "memory"},
                depends_on=memory_dependencies,
                priority=64,
            )
        if signals["proactive"]:
            proactive_dependencies = [main_chat_id]
            if analysis_ids:
                proactive_dependencies = analysis_ids[:1]
            add_lane(
                "proactive",
                f"Create proactive follow-up work and task tracking for: {objective}",
                title="Proactive Handoff",
                metadata={"role": "proactive"},
                depends_on=proactive_dependencies,
                priority=62,
            )
        if signals["connector"]:
            connector_dependencies = analysis_ids or [main_chat_id]
            add_lane(
                "connector",
                f"Coordinate connector-aware work or sync handoff for: {objective}",
                title="Connector Handoff",
                metadata={
                    "role": "connector",
                    "connectors": [term for term in connector_terms if term in tokens],
                },
                depends_on=connector_dependencies,
                priority=60,
            )

        graph_nodes: list[dict[str, Any]] = []
        graph_edges: list[dict[str, Any]] = []
        for index, lane in enumerate(lanes):
            world = "control"
            if lane["lane_type"] in {"research", "analysis", "writer", "executor"}:
                world = "parallel"
            elif lane["lane_type"] in {"memory", "proactive"}:
                world = "background"
            elif lane["lane_type"] == "connector":
                world = "connectors"
            elif lane["lane_type"] == "approval":
                world = "control"
            elif lane["lane_type"] == "main_chat":
                world = "control"
            graph_nodes.append(
                {
                    "id": lane["lane_id"],
                    "label": lane["title"],
                    "kind": lane["lane_type"],
                    "world": world,
                    "x": (index % 4) * 240 - 360,
                    "y": (index // 4) * 180 - 180,
                    "z": 100 + index * 8,
                    "status": lane["status"],
                    "tone": (
                        "cyan"
                        if lane["lane_type"] in {"main_chat", "research"}
                        else (
                            "violet"
                            if lane["lane_type"] in {"analysis", "connector"}
                            else (
                                "emerald"
                                if lane["lane_type"] in {"memory", "proactive"}
                                else (
                                    "amber"
                                    if lane["lane_type"] == "approval"
                                    else "slate"
                                )
                            )
                        )
                    ),
                    "meta": {
                        "depends_on": lane.get("depends_on") or [],
                        "blocked_by": lane.get("blocked_by") or [],
                        "priority": lane.get("priority"),
                        "role": lane.get("metadata", {}).get("role"),
                        "subagent_type": lane.get("subagent_type"),
                    },
                }
            )
            for dep in lane.get("depends_on") or []:
                graph_edges.append(
                    {
                        "source": dep,
                        "target": lane["lane_id"],
                        "label": "depends",
                        "tone": "cyan",
                        "kind": "dependency",
                    }
                )
            for blocker in lane.get("blocked_by") or []:
                graph_edges.append(
                    {
                        "source": blocker,
                        "target": lane["lane_id"],
                        "label": "blocks",
                        "tone": "amber",
                        "kind": "approval",
                    }
                )

        graph = {
            "nodes": graph_nodes,
            "edges": graph_edges,
            "worlds": [
                {
                    "id": "control",
                    "label": "Mission Control",
                    "description": "AverQel core, planner, approval queue, and synthesis.",
                },
                {
                    "id": "parallel",
                    "label": "Parallel Workers",
                    "description": "Research, analysis, and execution lanes.",
                },
                {
                    "id": "background",
                    "label": "Background Continuity",
                    "description": "Memory and proactive work continuation.",
                },
                {
                    "id": "connectors",
                    "label": "Connector Plane",
                    "description": "Integrations, sync handoff, and external systems.",
                },
            ],
        }

        return {
            "objective": objective,
            "note_content": note_content,
            "execution_mode": execution_mode,
            "signals": signals,
            "parallelizable": True,
            "approval_queue": approval_queue,
            "lanes": lanes,
            "graph": graph,
            "safety": {
                "gated_actions_detected": bool(approval_queue),
                "lane_count": len(lanes),
                "parallel_lane_count": len(
                    [
                        lane
                        for lane in lanes
                        if lane["lane_type"] not in {"main_chat", "approval"}
                    ]
                ),
                "dynamic_fanout": len(research_ids) + len(analysis_ids),
            },
        }

    def _combine_lane_outputs(self, lane_results: list[MissionLaneResult]) -> str:
        chunks = [result.summary for result in lane_results if result.summary.strip()]
        return "\n\n".join(chunks)[:8000] if chunks else ""

    async def _synthesize_mission_output(
        self,
        *,
        objective: str,
        plan: dict[str, Any],
        main_answer: str,
        lane_results: list[MissionLaneResult],
        note_content: str | None = None,
    ) -> str | None:
        synthesis_messages = [
            {
                "role": "system",
                "content": (
                    "You are the global orchestrator synthesizing multiple parallel mission lanes into one concise, accurate answer. "
                    "Respect approvals, never invent lane outputs, and mention unresolved approvals explicitly."
                ),
            },
            {"role": "system", "content": f"MISSION PLAN JSON:\n{plan}"},
        ]
        if note_content:
            synthesis_messages.append(
                {"role": "system", "content": f"WORKSPACE CONTEXT:\n{note_content}"}
            )
        synthesis_messages.append({"role": "user", "content": objective})
        synthesis_messages.append(
            {
                "role": "system",
                "content": (
                    "MAIN CHAT OUTPUT:\n"
                    f"{main_answer}\n\n"
                    "PARALLEL LANE OUTPUTS:\n"
                    + "\n".join(
                        f"- {lane.lane_id} [{lane.lane_type}] ({lane.status}): {lane.summary}"
                        for lane in lane_results
                    )
                ),
            }
        )
        request = ChatGenerateRequest(
            model=self.agent.model_name or self.settings.llm_model,
            messages=synthesis_messages,
            temperature=0.1,
            max_tokens=1400,
            base_url=self.agent.base_url or self.settings.llm_api_base_url,
            api_key=self.agent.api_key,
            tools=[],
            reasoning_enabled=True,
            metadata={
                "provider_type": self.agent.provider_type or self.settings.llm_provider,
                "timeout_seconds": float(self.settings.provider_timeout_seconds),
                "orchestration": True,
            },
        )
        try:
            result = await asyncio.to_thread(self.agent.llm.generate, request)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Mission synthesis failed: %s", exc, exc_info=True)
            return main_answer or None
        text = (result.content or "").strip()
        return text[:8000] if text else (main_answer or None)
