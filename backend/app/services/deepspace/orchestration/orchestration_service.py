from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.auth import AuthContext
from app.core.config import Settings
from app.models.deepspace.agent_activity import AgentActivity
from app.services.deepspace.execution.agent_executor import AgentExecutor
from app.services.deepspace.execution.agent_tools import ALL_TOOLS
from app.services.deepspace.memory.memory_service import TodoService
from app.services.deepspace.missions.mission_registry import MissionRegistry
from app.services.deepspace.subagents.subagent_registry import SubagentRegistry
from app.services.system.vitals_service import VitalsService

logger = logging.getLogger(__name__)

GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


class OrchestrationService:
    """Build a unified orchestration snapshot for OpenChat, subagents, and proactive work."""

    async def get_orchestration_overview(
        self,
        *,
        auth: AuthContext,
        db: Session,
        settings: Settings,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        vitals = await VitalsService.get_system_vitals(auth.tenant_id)
        runtime = self._get_runtime_snapshot(auth=auth, db=db, settings=settings)
        registry = SubagentRegistry(settings)
        mission_registry = MissionRegistry(settings, db=db)
        todo_service = TodoService(db)

        subagent_runs = registry.list_runs(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
            limit=24,
        )
        active_missions = mission_registry.active_missions(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
            limit=12,
        )
        tasks = await todo_service.list_todos(
            tenant_id=str(auth.tenant_id),
            user_id=str(auth.user_id),
        )

        # Filter by conversation_id if provided
        matching_mission_ids: set[str] = set()
        if conversation_id:
            active_missions = [
                m
                for m in active_missions
                if str(m.get("parent_id") or "") == str(conversation_id)
                or str(m.get("mission_id") or "") == str(conversation_id)
            ]
            matching_mission_ids = {str(m.get("mission_id")) for m in active_missions}
            matching_mission_ids.add(str(conversation_id))

            subagent_runs = [
                run
                for run in subagent_runs
                if str(run.get("parent_id") or "") in matching_mission_ids
            ]
            tasks = [
                task
                for task in tasks
                if str(task.get("thread_id") or "") == str(conversation_id)
            ]

        activities = self._get_recent_activities(
            db=db,
            tenant_id=auth.tenant_id,
            conversation_id=conversation_id,
            matching_mission_ids=matching_mission_ids,
        )
        tool_catalog = [tool.name for tool in ALL_TOOLS]
        active_tools = list(runtime.get("active_tools") or [])

        graph = self._build_mission_graph(
            vitals=vitals,
            runtime=runtime,
            subagent_runs=subagent_runs,
            tasks=tasks,
            activities=activities,
            tool_catalog=tool_catalog,
            daemon_heartbeat=registry.get_daemon_heartbeat(),
            active_missions=active_missions,
        )

        activity_types = Counter(
            str(activity.get("type") or "unknown") for activity in activities
        )
        connector_statuses = dict(vitals.get("connector_statuses") or {})
        active_subagents = [
            run
            for run in subagent_runs
            if str(run.get("status") or "").lower() == "running"
        ]
        active_tasks = [
            task
            for task in tasks
            if str(task.get("status") or "").lower() in {"pending", "in_progress"}
        ]

        return {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runtime": runtime,
            "vitals": vitals,
            "subagents": {
                "runs": subagent_runs,
                "active": active_subagents,
                "max_concurrency": registry.max_concurrency,
                "daemon_heartbeat": registry.get_daemon_heartbeat(),
            },
            "tasks": {
                "all": tasks,
                "active": active_tasks,
            },
            "activities": activities,
            "missions": {
                "active": active_missions,
                "count": len(active_missions),
                "heartbeat": mission_registry.get_heartbeat(
                    tenant_id=str(auth.tenant_id),
                    user_id=str(auth.user_id),
                ),
                "execution_mode": mission_registry.get_execution_mode(
                    tenant_id=str(auth.tenant_id),
                    user_id=str(auth.user_id),
                ),
            },
            "tool_catalog": {
                "count": len(tool_catalog),
                "names": tool_catalog,
                "active": active_tools,
            },
            "summary": {
                "active_subagents": len(active_subagents),
                "active_tasks": len(active_tasks),
                "recent_activities": len(activities),
                "tool_count": len(tool_catalog),
                "connector_count": int(vitals.get("sources") or 0),
                "parallel_capacity": registry.max_concurrency,
                "activity_types": dict(activity_types),
                "connector_statuses": connector_statuses,
                "daemon_healthy": bool(
                    (vitals.get("proactive_daemon") or {}).get("healthy")
                ),
            },
            "graph": graph,
        }

    def _get_runtime_snapshot(
        self,
        *,
        auth: AuthContext,
        db: Session,
        settings: Settings,
    ) -> dict[str, Any]:
        try:
            executor = AgentExecutor(db=db, auth=auth, settings=settings)
            return {
                "model_name": executor.model_name,
                "provider_type": executor.provider_type,
                "context_limit": executor.reported_context_limit,
                "context_limit_source": executor.context_limit_source,
                "tool_count": len(ALL_TOOLS),
                "execution_mode": MissionRegistry(settings, db=db).get_execution_mode(
                    tenant_id=str(auth.tenant_id),
                    user_id=str(auth.user_id),
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Falling back to orchestration runtime defaults for tenant %s user %s: %s",
                auth.tenant_id,
                auth.user_id,
                exc,
                exc_info=True,
            )
            return {
                "model_name": settings.llm_model or None,
                "provider_type": settings.llm_provider,
                "context_limit": None,
                "context_limit_source": "unknown",
                "tool_count": len(ALL_TOOLS),
                "execution_mode": MissionRegistry(settings, db=db).get_execution_mode(
                    tenant_id=str(auth.tenant_id),
                    user_id=str(auth.user_id),
                ),
            }

    def _get_recent_activities(
        self,
        *,
        db: Session,
        tenant_id: Any,
        limit: int = 18,
        conversation_id: str | None = None,
        matching_mission_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        query_limit = 200 if conversation_id else limit
        rows = (
            db.query(AgentActivity)
            .filter(AgentActivity.tenant_id == tenant_id)
            .order_by(desc(AgentActivity.created_at))
            .limit(query_limit)
            .all()
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            meta = dict(row.metadata_json or {})
            if conversation_id:
                row_mission_id = str(meta.get("mission_id") or "")
                row_conv_id = str(meta.get("conversation_id") or "")
                is_match = (
                    row_conv_id == str(conversation_id)
                    or (matching_mission_ids and row_mission_id in matching_mission_ids)
                    or row_mission_id == str(conversation_id)
                )
                if not is_match:
                    continue

            result.append(
                {
                    "id": str(row.id),
                    "type": row.activity_type,
                    "description": row.description,
                    "source": row.source,
                    "metadata_json": meta,
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                }
            )
            if len(result) >= limit:
                break
        return result

    def _build_mission_graph(
        self,
        *,
        vitals: dict[str, Any],
        runtime: dict[str, Any],
        subagent_runs: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        activities: list[dict[str, Any]],
        tool_catalog: list[str],
        daemon_heartbeat: dict[str, Any] | None,
        active_missions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        def add_node(
            node_id: str,
            *,
            label: str,
            kind: str,
            world: str,
            x: float,
            y: float,
            z: float,
            status: str,
            tone: str,
            meta: dict[str, Any] | None = None,
        ) -> None:
            nodes.append(
                {
                    "id": node_id,
                    "label": label,
                    "kind": kind,
                    "world": world,
                    "x": x,
                    "y": y,
                    "z": z,
                    "status": status,
                    "tone": tone,
                    "meta": meta or {},
                }
            )

        def add_edge(
            source: str,
            target: str,
            *,
            label: str,
            tone: str,
            kind: str,
        ) -> None:
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "label": label,
                    "tone": tone,
                    "kind": kind,
                }
            )

        def spiral_position(
            index: int, radius: float, *, phase: float = 0.0
        ) -> tuple[float, float]:
            angle = phase + index * GOLDEN_ANGLE
            return math.cos(angle) * radius, math.sin(angle) * radius * 0.72

        def status_tone(value: str) -> str:
            normalized = value.lower()
            if normalized in {"running", "active", "connected", "available", "healthy"}:
                return "emerald"
            if normalized in {"pending", "paused", "waiting", "scheduled"}:
                return "amber"
            if normalized in {"error", "failed", "degraded", "stale", "terminating"}:
                return "rose"
            return "slate"

        # Core control plane.
        add_node(
            "open_chat",
            label="AverQel Mission Core",
            kind="core",
            world="control",
            x=0.0,
            y=0.0,
            z=120.0,
            status="active",
            tone="primary",
            meta={
                "model_name": runtime.get("model_name"),
                "provider_type": runtime.get("provider_type"),
                "context_limit": runtime.get("context_limit"),
                "context_limit_source": runtime.get("context_limit_source"),
            },
        )
        add_node(
            "mission_router",
            label="Mission Router",
            kind="planner",
            world="control",
            x=-350.0,
            y=-150.0,
            z=90.0,
            status="active",
            tone="cyan",
            meta={
                "description": "Selects plans, tools, subagents, and approvals.",
            },
        )
        add_node(
            "tool_executor",
            label=f"Tool Executor · {len(tool_catalog)} tools",
            kind="executor",
            world="control",
            x=350.0,
            y=-150.0,
            z=90.0,
            status="active",
            tone="violet",
            meta={
                "active_tools": tool_catalog[:20],
                "tool_count": len(tool_catalog),
            },
        )
        add_node(
            "approval_gate",
            label="Approval Gate",
            kind="guard",
            world="control",
            x=0.0,
            y=180.0,
            z=70.0,
            status="waiting",
            tone="amber",
            meta={
                "description": "Pauses risky or destructive actions until the user decides.",
            },
        )
        add_node(
            "mission_output",
            label="Synthesized Output",
            kind="output",
            world="control",
            x=0.0,
            y=380.0,
            z=60.0,
            status="active",
            tone="emerald",
            meta={
                "description": "Final answer, verifications, summaries, and handoff.",
            },
        )

        add_edge(
            "open_chat", "mission_router", label="intent", tone="cyan", kind="reason"
        )
        add_edge(
            "mission_router",
            "tool_executor",
            label="dispatch",
            tone="violet",
            kind="tool",
        )
        add_edge(
            "tool_executor",
            "approval_gate",
            label="gate",
            tone="amber",
            kind="approval",
        )
        add_edge(
            "approval_gate",
            "mission_output",
            label="resume",
            tone="emerald",
            kind="synthesis",
        )
        add_edge(
            "tool_executor",
            "mission_output",
            label="verify",
            tone="emerald",
            kind="synthesis",
        )
        add_edge(
            "mission_router",
            "mission_output",
            label="synthesis",
            tone="emerald",
            kind="synthesis",
        )

        if active_missions:
            add_node(
                "mission_fleet",
                label=f"Mission Fleet · {len(active_missions)} active",
                kind="signal",
                world="control",
                x=-650.0,
                y=-450.0,
                z=100.0,
                status="active",
                tone="cyan",
                meta={
                    "active_missions": len(active_missions),
                    "latest_status": (
                        active_missions[0].get("status") if active_missions else None
                    ),
                },
            )
            add_edge(
                "mission_router",
                "mission_fleet",
                label="route",
                tone="cyan",
                kind="reason",
            )
            add_edge(
                "mission_fleet",
                "mission_output",
                label="synthesize",
                tone="emerald",
                kind="synthesis",
            )
            for index, mission in enumerate(active_missions[:8]):
                offset_x, offset_y = spiral_position(index, 240.0, phase=2.0)
                mission_status = str(mission.get("status") or "unknown")
                mission_id = str(mission.get("mission_id") or f"mission_{index}")
                add_node(
                    f"mission_{mission_id}",
                    label=str(mission.get("objective") or mission_id),
                    kind="signal",
                    world="control",
                    x=-650.0 + offset_x * 0.7,
                    y=-450.0 + offset_y * 0.55,
                    z=120.0 + index * 6.0,
                    status=mission_status,
                    tone=status_tone(mission_status),
                    meta={
                        "mission_id": mission_id,
                        "summary": mission.get("summary") or "",
                        "last_event_type": mission.get("last_event_type"),
                        "approval_queue": mission.get("approval_queue") or [],
                        "lane_count": len(mission.get("lane_states") or []),
                    },
                )
                add_edge(
                    "mission_fleet",
                    f"mission_{mission_id}",
                    label="mission",
                    tone="cyan",
                    kind="reason",
                )

        # Memory / ledger lane.
        add_node(
            "memory_ledger",
            label="Memory Ledger",
            kind="ledger",
            world="memory",
            x=-350.0,
            y=150.0,
            z=80.0,
            status="active",
            tone="cyan",
            meta={"description": "Tasks, facts, and work state."},
        )
        add_edge(
            "tool_executor", "memory_ledger", label="ledger", tone="cyan", kind="memory"
        )
        add_edge(
            "memory_ledger",
            "mission_output",
            label="context",
            tone="cyan",
            kind="memory",
        )

        # Proactive workspace lane.
        add_node(
            "proactive_workspace",
            label="Proactive Workspace",
            kind="workspace",
            world="background",
            x=350.0,
            y=150.0,
            z=50.0,
            status="active" if tasks else "idle",
            tone="emerald" if tasks else "slate",
            meta={
                "active_tasks": len(
                    [
                        task
                        for task in tasks
                        if str(task.get("status") or "").lower()
                        in {"pending", "in_progress"}
                    ]
                ),
                "recurring_tasks": len(
                    [task for task in tasks if task.get("is_recurring")]
                ),
            },
        )
        add_edge(
            "open_chat",
            "proactive_workspace",
            label="handoff",
            tone="emerald",
            kind="task",
        )
        add_edge(
            "proactive_workspace",
            "memory_ledger",
            label="persist",
            tone="cyan",
            kind="memory",
        )

        # Connector lane.
        add_node(
            "connector_mesh",
            label="Connector Mesh",
            kind="connector",
            world="connectors",
            x=650.0,
            y=0.0,
            z=85.0,
            status="active" if int(vitals.get("sources") or 0) > 0 else "idle",
            tone="violet",
            meta={
                "sources": int(vitals.get("sources") or 0),
                "connector_statuses": dict(vitals.get("connector_statuses") or {}),
            },
        )
        add_edge(
            "tool_executor",
            "connector_mesh",
            label="integrate",
            tone="violet",
            kind="connector",
        )
        add_edge(
            "connector_mesh",
            "memory_ledger",
            label="index",
            tone="violet",
            kind="memory",
        )

        # System vitals lane.
        add_node(
            "system_internet",
            label="Internet",
            kind="system",
            world="systems",
            x=-650.0,
            y=-300.0,
            z=30.0,
            status=str(vitals.get("internet") or "unknown"),
            tone=status_tone(str(vitals.get("internet") or "unknown")),
            meta={"value": vitals.get("internet")},
        )
        add_node(
            "system_llm",
            label="LLM Runtime",
            kind="system",
            world="systems",
            x=650.0,
            y=-150.0,
            z=30.0,
            status=str(vitals.get("llm") or "unknown"),
            tone=status_tone(str(vitals.get("llm") or "unknown")),
            meta={"value": vitals.get("llm")},
        )
        add_node(
            "system_search",
            label="Web Search",
            kind="system",
            world="systems",
            x=-650.0,
            y=-150.0,
            z=30.0,
            status=str(vitals.get("web_search") or "unknown"),
            tone=status_tone(str(vitals.get("web_search") or "unknown")),
            meta={"value": vitals.get("web_search")},
        )
        add_node(
            "system_daemon",
            label="Proactive Daemon",
            kind="system",
            world="systems",
            x=650.0,
            y=150.0,
            z=30.0,
            status=(
                "healthy"
                if (vitals.get("proactive_daemon") or {}).get("healthy")
                else (
                    "stale"
                    if (vitals.get("proactive_daemon") or {}).get("enabled")
                    else "disabled"
                )
            ),
            tone=(
                "emerald"
                if (vitals.get("proactive_daemon") or {}).get("healthy")
                else (
                    "amber"
                    if (vitals.get("proactive_daemon") or {}).get("enabled")
                    else "slate"
                )
            ),
            meta=vitals.get("proactive_daemon") or {},
        )
        add_edge(
            "system_internet",
            "mission_router",
            label="reach",
            tone="cyan",
            kind="system",
        )
        add_edge(
            "system_llm", "tool_executor", label="reason", tone="violet", kind="system"
        )
        add_edge(
            "system_search",
            "mission_router",
            label="evidence",
            tone="emerald",
            kind="system",
        )
        add_edge(
            "system_daemon",
            "proactive_workspace",
            label="heartbeat",
            tone="amber",
            kind="system",
        )

        # Subagent swarm.
        if subagent_runs:
            add_node(
                "subagent_swarm",
                label=f"Subagent Swarm · {len(subagent_runs)} runs",
                kind="swarm",
                world="parallel",
                x=0.0,
                y=-350.0,
                z=120.0,
                status=(
                    "active"
                    if any(
                        str(run.get("status") or "").lower() == "running"
                        for run in subagent_runs
                    )
                    else "idle"
                ),
                tone="cyan",
                meta={
                    "active_runs": len(
                        [
                            run
                            for run in subagent_runs
                            if str(run.get("status") or "").lower() == "running"
                        ]
                    ),
                },
            )
            add_edge(
                "mission_router",
                "subagent_swarm",
                label="delegate",
                tone="cyan",
                kind="subagent",
            )
            add_edge(
                "subagent_swarm",
                "mission_output",
                label="synthesize",
                tone="emerald",
                kind="subagent",
            )

            for index, run in enumerate(subagent_runs[:12]):
                offset_x, offset_y = spiral_position(index, 280.0, phase=-0.3)
                run_status = str(run.get("status") or "unknown")
                node_id = f"subagent_{run.get('run_id')}"
                add_node(
                    node_id,
                    label=f"{run.get('subagent_type') or 'subagent'} · {run_status}",
                    kind="subagent",
                    world="parallel",
                    x=offset_x * 0.8,
                    y=-550.0 + offset_y * 0.5,
                    z=180.0 + index * 6.0,
                    status=run_status,
                    tone=status_tone(run_status),
                    meta={
                        "run_id": run.get("run_id"),
                        "slot_index": run.get("slot_index"),
                        "step_count": run.get("step_count"),
                        "summary": run.get("summary")
                        or run.get("last_event_message")
                        or "",
                        "prompt": run.get("prompt"),
                        "final_output": run.get("final_output"),
                        "error": run.get("error"),
                    },
                )
                add_edge(
                    "subagent_swarm",
                    node_id,
                    label="task",
                    tone="cyan",
                    kind="subagent",
                )

        # Task lane.
        if tasks:
            add_node(
                "task_queue",
                label=f"Task Queue · {len(tasks)} items",
                kind="queue",
                world="background",
                x=650.0,
                y=350.0,
                z=55.0,
                status=(
                    "active"
                    if any(task.get("enabled", True) for task in tasks)
                    else "idle"
                ),
                tone="emerald",
                meta={
                    "active_tasks": len(
                        [
                            task
                            for task in tasks
                            if str(task.get("status") or "").lower()
                            in {"pending", "in_progress"}
                        ]
                    ),
                },
            )
            add_edge(
                "proactive_workspace",
                "task_queue",
                label="schedule",
                tone="emerald",
                kind="task",
            )
            for index, task in enumerate(tasks[:12]):
                offset_x, offset_y = spiral_position(index, 330.0, phase=0.8)
                task_status = str(task.get("status") or "unknown")
                node_id = f"task_{task.get('id')}"
                add_node(
                    node_id,
                    label=str(task.get("activeForm") or task.get("content") or "task"),
                    kind="task",
                    world="background",
                    x=650.0 + offset_x * 0.78,
                    y=550.0 + offset_y * 0.36,
                    z=110.0 + index * 4.0,
                    status=task_status,
                    tone=status_tone(task_status),
                    meta={
                        "task_id": task.get("id"),
                        "priority": task.get("priority"),
                        "is_recurring": task.get("is_recurring"),
                        "enabled": task.get("enabled"),
                        "next_run_at": task.get("next_run_at"),
                        "last_run_at": task.get("last_run_at"),
                        "automation_json": task.get("automation_json") or {},
                    },
                )
                add_edge(
                    "task_queue", node_id, label="slot", tone="emerald", kind="task"
                )

        # Activity lane.
        if activities:
            add_node(
                "activity_stream",
                label=f"Activity Stream · {len(activities)} events",
                kind="stream",
                world="surface",
                x=-650.0,
                y=0.0,
                z=45.0,
                status="active",
                tone="rose",
                meta={
                    "types": dict(
                        Counter(
                            str(item.get("type") or "unknown") for item in activities
                        )
                    ),
                },
            )
            add_edge(
                "activity_stream",
                "mission_router",
                label="signal",
                tone="rose",
                kind="activity",
            )
            for index, activity in enumerate(activities[:12]):
                offset_x, offset_y = spiral_position(index, 310.0, phase=1.4)
                node_id = f"activity_{activity.get('id')}"
                add_node(
                    node_id,
                    label=str(
                        activity.get("description")
                        or activity.get("type")
                        or "activity"
                    ),
                    kind="activity",
                    world="surface",
                    x=-650.0 + offset_x * 0.52,
                    y=0.0 + offset_y * 0.48,
                    z=60.0 + index * 2.0,
                    status=str(activity.get("type") or "unknown"),
                    tone=status_tone(str(activity.get("type") or "unknown")),
                    meta={
                        "activity_id": activity.get("id"),
                        "source": activity.get("source"),
                        "created_at": activity.get("created_at"),
                        "metadata_json": activity.get("metadata_json") or {},
                    },
                )
                source_kind = str(activity.get("source") or "activity")
                edge_kind = (
                    "connector"
                    if source_kind
                    in {"gmail", "calendar", "drive", "github", "notion", "slack"}
                    else "activity"
                )
                add_edge(
                    "activity_stream",
                    node_id,
                    label=source_kind,
                    tone="rose",
                    kind=edge_kind,
                )

        # Tool catalog spine.
        add_node(
            "tool_catalog",
            label=f"Tool Catalog · {len(tool_catalog)}",
            kind="catalog",
            world="systems",
            x=650.0,
            y=-300.0,
            z=55.0,
            status="active" if tool_catalog else "idle",
            tone="violet",
            meta={
                "sample_tools": tool_catalog[:18],
                "tool_count": len(tool_catalog),
            },
        )
        add_edge(
            "tool_catalog", "tool_executor", label="invoke", tone="violet", kind="tool"
        )

        if daemon_heartbeat:
            heartbeat_label = str(daemon_heartbeat.get("phase") or "running").replace(
                "_", " "
            )
            add_node(
                "daemon_heartbeat",
                label=f"Daemon Heartbeat · {heartbeat_label}",
                kind="signal",
                world="systems",
                x=850.0,
                y=150.0,
                z=40.0,
                status=heartbeat_label,
                tone="amber",
                meta=daemon_heartbeat,
            )
            add_edge(
                "daemon_heartbeat",
                "system_daemon",
                label="pulse",
                tone="amber",
                kind="system",
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "worlds": [
                {
                    "id": "control",
                    "label": "Mission Control",
                    "description": "Main AverQel planning, execution, approval, and synthesis plane.",
                },
                {
                    "id": "parallel",
                    "label": "Parallel Workers",
                    "description": "Subagents and fan-out reasoning lanes.",
                },
                {
                    "id": "background",
                    "label": "Proactive Layer",
                    "description": "24/7 tasks, recurring jobs, and workspace automation.",
                },
                {
                    "id": "systems",
                    "label": "System Mesh",
                    "description": "LLM, internet, search, connector, and daemon health.",
                },
                {
                    "id": "memory",
                    "label": "Memory",
                    "description": "Ledger and knowledge continuity across work.",
                },
                {
                    "id": "connectors",
                    "label": "Connector Plane",
                    "description": "Google, GitHub, Slack, Drive, Calendar, and other integrations.",
                },
                {
                    "id": "surface",
                    "label": "Activity Surface",
                    "description": "Recent events and evidence flowing into the mission.",
                },
            ],
        }
