from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from app.core.brand import APP_BRAND_NAME
from app.core.config import Settings
from app.deepspace.execution.agent_executor import AgentExecutor
from app.deepspace.planning.planner_validation import (
    ALLOWED_LANE_TYPES,
    parse_planner_json_payload,
    sanitize_approval_queue,
    sanitize_lane_blueprints,
    validate_planner_payload,
)
from app.providers.services.reasoning_capabilities import reasoning_capabilities
from app.providers.services.types import ChatGenerateRequest

logger = logging.getLogger(__name__)


class MissionPlanner:
    """Build a policy-aware or model-authored mission plan JSON."""

    def __init__(self, *, agent: AgentExecutor, settings: Settings) -> None:
        self.agent = agent
        self.settings = settings

    async def build_plan(
        self,
        *,
        objective: str,
        note_content: str | None = None,
        execution_mode: str = "auto_review",
        planner_mode: str = "default",
        on_event: Callable[[str, Any], Any] | None = None,
    ) -> dict[str, Any]:
        normalized_execution_mode = (
            "full_access"
            if str(execution_mode).strip().lower() == "full_access"
            else "auto_review"
        )
        normalized_planner_mode = (
            "structured"
            if str(planner_mode).strip().lower() == "structured"
            else "default"
        )
        planner_json = await self._try_model_planner_json(
            objective=objective,
            note_content=note_content,
            execution_mode=normalized_execution_mode,
            planner_mode=normalized_planner_mode,
            on_event=on_event,
        )
        if planner_json is None:
            # Never fabricate a coding/research graph when the model planner
            # failed. The caller can retry or surface a clear planning error;
            # invented plans create actions the user never requested.
            raise RuntimeError("MODEL_PLANNER_UNAVAILABLE")
        return self._materialize_plan(
            planner_json,
            objective=objective,
            note_content=note_content,
            execution_mode=normalized_execution_mode,
            planner_mode=normalized_planner_mode,
        )

    async def _try_model_planner_json(
        self,
        *,
        objective: str,
        note_content: str | None,
        execution_mode: str,
        planner_mode: str,
        on_event: Callable[[str, Any], Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            model_name = self.agent.model_name or self.settings.llm_model
            provider_type = self.agent.provider_type or self.settings.llm_provider
            base_url = self.agent.base_url or self.settings.llm_api_base_url
            api_key = self.agent.api_key
            planning_messages = [
                {
                    "role": "system",
                    "content": (
                        f"You are the {APP_BRAND_NAME} mission planner. Return JSON only, with no markdown or commentary. "
                        "Build a compact mission plan for the orchestration layer. "
                        "Use only these lane types: main_chat, research, analysis, writer, executor, memory, proactive, connector, support, approval. "
                        "Support lanes may be used for system vitals, daemon heartbeat, and connector health sweeps. "
                        "Always include one main_chat blueprint. Use refs for depends_on and blocked_by. "
                        "If execution_mode is auto_review and the mission includes destructive or gated work, include an approval blueprint. "
                        "If execution_mode is full_access, do not include approval blueprints unless an explicit operator checkpoint is required by policy. "
                        "Return a compact JSON object with these keys: planner_source, summary, parallel_limit, signals, approval_queue, lane_blueprints. "
                        "Each lane blueprint must include ref, lane_type, title, prompt, priority, depends_on, blocked_by, subagent_type, and metadata."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "objective": objective,
                            "note_content": note_content or "",
                            "execution_mode": execution_mode,
                            "planner_mode": planner_mode,
                            "guidance": {
                                "keep_the_plan_small": True,
                                "must_include_main_chat": True,
                                "respect_approval_policy": True,
                                "prefer_parallel_safe_work": True,
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
            request = ChatGenerateRequest(
                model=model_name,
                messages=planning_messages,
                temperature=0.0,
                max_tokens=1200,
                base_url=base_url,
                api_key=api_key,
                reasoning_enabled=bool(
                    reasoning_capabilities(
                        provider_type,
                        model_name,
                        base_url=base_url,
                    ).get("supports_reasoning")
                ),
                metadata={
                    "provider_type": provider_type,
                    "timeout_seconds": float(self.settings.provider_timeout_seconds),
                    "planner": True,
                },
            )
            if hasattr(self.agent, "_stream_llm_events_with_timeout"):
                plan_text_parts = []
                async for event in self.agent._stream_llm_events_with_timeout(request):
                    if event["type"] == "thinking":
                        if on_event:
                            await on_event("thinking", event["text"])
                    elif event["type"] == "delta":
                        plan_text_parts.append(event["text"])
                raw_text = "".join(plan_text_parts).strip()
            else:
                result = await asyncio.to_thread(self.agent.llm.generate, request)
                raw_text = getattr(result, "content", None) or str(result or "")
            parsed = parse_planner_json_payload(raw_text)
            validated = validate_planner_payload(parsed)
            if validated and validated.get("lane_blueprints"):
                validated["planner_source"] = "model"
                validated["planner_mode"] = planner_mode
                return validated
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Mission planner JSON generation fell back: %s", exc, exc_info=True
            )

    def _policy_planner_json(
        self,
        *,
        objective: str,
        note_content: str | None,
        execution_mode: str,
        planner_mode: str,
    ) -> dict[str, Any]:
        """Removed: plans must come from the model controller."""
        raise RuntimeError("MODEL_POLICY_PLANNER_REMOVED")
        """
        recursive_proactive = "create proactive follow-up work" in normalized_objective
        proactive_requested = "proactive" in normalized_objective and not recursive_proactive
        blueprints: list[dict[str, Any]] = []
        if classification.task_type == "coding":
            blueprints = [
                {"ref": "inspect", "lane_type": "analysis", "title": "Inspect and diagnose", "prompt": f"Inspect the repository and diagnose: {objective}", "priority": 100, "depends_on": [], "blocked_by": [], "subagent_type": "analysis", "metadata": {"role": "reviewer", "phase": "understand"}},
                {"ref": "implement", "lane_type": "executor", "title": "Implement the change", "prompt": objective, "priority": 90, "depends_on": ["inspect"], "blocked_by": [], "subagent_type": "implementer", "metadata": {"role": "implementer", "phase": "implement"}},
                {"ref": "verify", "lane_type": "executor", "title": "Run verification", "prompt": f"Run tests and verification for: {objective}", "priority": 80, "depends_on": ["implement"], "blocked_by": [], "subagent_type": "tester", "metadata": {"role": "tester", "phase": "test"}},
                {"ref": "review", "lane_type": "analysis", "title": "Review evidence and diff", "prompt": f"Review the implementation, test evidence, and diff for: {objective}", "priority": 70, "depends_on": ["verify"], "blocked_by": [], "subagent_type": "reviewer", "metadata": {"role": "reviewer", "phase": "review"}},
                {"ref": "main_chat", "lane_type": "main_chat", "title": "Report verified result", "prompt": objective, "priority": 60, "depends_on": ["review"], "blocked_by": [], "subagent_type": None, "metadata": {"role": "primary", "phase": "report"}},
            ]
        elif classification.task_type == "research":
            blueprints = [
                {"ref": "collect", "lane_type": "research", "title": "Collect evidence", "prompt": objective, "priority": 100, "depends_on": [], "blocked_by": [], "subagent_type": "research", "metadata": {"phase": "collect"}},
                {"ref": "compare", "lane_type": "analysis", "title": "Compare evidence", "prompt": objective, "priority": 80, "depends_on": ["collect"], "blocked_by": [], "subagent_type": "analysis", "metadata": {"phase": "compare"}},
                {"ref": "synthesize", "lane_type": "writer", "title": "Synthesize findings", "prompt": objective, "priority": 70, "depends_on": ["compare"], "blocked_by": [], "subagent_type": "writer", "metadata": {"phase": "synthesize"}},
                {"ref": "main_chat", "lane_type": "main_chat", "title": "Report findings", "prompt": objective, "priority": 60, "depends_on": ["synthesize"], "blocked_by": [], "subagent_type": None, "metadata": {"role": "primary", "phase": "report"}},
            ]
        elif classification.task_type == "automation":
            blueprints = [
                {"ref": "validate", "lane_type": "analysis", "title": "Validate automation", "prompt": objective, "priority": 100, "depends_on": [], "blocked_by": [], "subagent_type": "analysis", "metadata": {"phase": "validate"}},
                {"ref": "execute", "lane_type": "executor", "title": "Execute approved work", "prompt": objective, "priority": 80, "depends_on": ["validate"], "blocked_by": [], "subagent_type": "executor", "metadata": {"phase": "execute"}},
                {"ref": "verify", "lane_type": "analysis", "title": "Verify outcome", "prompt": objective, "priority": 70, "depends_on": ["execute"], "blocked_by": [], "subagent_type": "reviewer", "metadata": {"phase": "verify"}},
                {"ref": "main_chat", "lane_type": "main_chat", "title": "Report outcome", "prompt": objective, "priority": 60, "depends_on": ["verify"], "blocked_by": [], "subagent_type": None, "metadata": {"role": "primary", "phase": "report"}},
            ]
        else:
            blueprints = [{"ref": "main_chat", "lane_type": "main_chat", "title": "Autonomous Execution", "prompt": objective, "priority": 100, "depends_on": [], "blocked_by": [], "subagent_type": None, "metadata": {"role": "primary", "autonomous": True}}]
        return {
            "planner_source": "policy",
            "planner_mode": planner_mode,
            "planner_version": 2,
            "objective": objective,
            "acceptance_criteria": list(
                GoalContract.from_request(objective).acceptance_criteria
            ),
            "note_content": note_content,
            "execution_mode": execution_mode,
            "summary": f"Autonomous execution for: {objective}",
            "signals": {
                "research": False,
                "analysis": False,
                "writer": False,
                "executor": False,
                "memory": False,
                "proactive": proactive_requested,
                "support": False,
                "approval": False,
                "connector": False,
            },
            "parallel_limit": 1,
            "approval_queue": [],
            "classification": classification.to_dict(),
            "lane_blueprints": blueprints,
            "safety": {
                "gated_actions_detected": False,
                "lane_count": 1,
                "parallel_lane_count": 0,
                "dynamic_fanout": 0,
            },
        }
        """

    @staticmethod
    def _add_blueprint(
        lane_blueprints: list[dict[str, Any]],
        *,
        ref: str,
        lane_type: str,
        title: str,
        prompt: str,
        priority: int,
        depends_on: list[str] | None = None,
        blocked_by: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        subagent_type: str | None = None,
    ) -> str:
        lane_blueprints.append(
            {
                "ref": ref,
                "lane_type": lane_type,
                "title": title,
                "prompt": prompt,
                "priority": priority,
                "depends_on": list(depends_on or []),
                "blocked_by": list(blocked_by or []),
                "subagent_type": subagent_type,
                "metadata": metadata or {},
            }
        )
        return ref

    @staticmethod
    def _summarize_planner(objective: str, signals: dict[str, bool]) -> str:
        activated = [name for name, active in signals.items() if active]
        if not activated:
            return f"Mission plan for: {objective}"
        return f"Mission plan for: {objective} | lanes: {', '.join(activated)}"

    def _materialize_plan(
        self,
        planner_json: dict[str, Any],
        *,
        objective: str,
        note_content: str | None,
        execution_mode: str,
        planner_mode: str,
    ) -> dict[str, Any]:
        # Suppress proactive recursive generation if needed
        suppress_proactive = False
        normalized_obj = objective.lower()
        if (
            "create proactive follow-up work" in normalized_obj
            or "restore proactive capacity" in normalized_obj
            or "investigate gmail proactive message failure" in normalized_obj
            or "investigate gmail proactive scan failure" in normalized_obj
        ):
            suppress_proactive = True

        raw_lane_blueprints = [
            blueprint
            for blueprint in list(planner_json.get("lane_blueprints") or [])
            if isinstance(blueprint, dict)
        ]
        if suppress_proactive:
            raw_lane_blueprints = [
                bp for bp in raw_lane_blueprints if bp.get("lane_type") != "proactive"
            ]

        normalized_execution_mode = (
            "full_access"
            if str(execution_mode).strip().lower() == "full_access"
            else "auto_review"
        )
        sanitized_blueprints = sanitize_lane_blueprints(
            raw_lane_blueprints,
            objective=objective,
            execution_mode=normalized_execution_mode,
            allowed_lane_types=ALLOWED_LANE_TYPES,
        )
        signals = (
            planner_json.get("signals")
            if isinstance(planner_json.get("signals"), dict)
            else {}
        )
        auto_signals = {
            "research": bool(signals.get("research")),
            "analysis": bool(signals.get("analysis")),
            "writer": bool(signals.get("writer")),
            "executor": bool(signals.get("executor")),
            "memory": bool(signals.get("memory")),
            "proactive": bool(signals.get("proactive")) and not suppress_proactive,
            "support": bool(signals.get("support")),
            "approval": bool(signals.get("approval")),
            "connector": bool(signals.get("connector")),
        }

        if not sanitized_blueprints:
            raise RuntimeError("MODEL_PLANNER_RETURNED_NO_ACTIONS")

        if not any(
            str(item.get("lane_type") or "") == "main_chat"
            for item in sanitized_blueprints
        ):
            sanitized_blueprints.insert(
                0,
                {
                    "ref": "main_chat",
                    "lane_type": "main_chat",
                    "title": "AverQel Mission Core",
                    "prompt": objective,
                    "priority": 100,
                    "depends_on": [],
                    "blocked_by": [],
                    "subagent_type": None,
                    "metadata": {"role": "primary"},
                },
            )

        if auto_signals["support"] and not any(
            blueprint["lane_type"] == "support" for blueprint in sanitized_blueprints
        ):
            support_dependencies = [
                blueprint["ref"] for blueprint in sanitized_blueprints[:1]
            ] or ["main_chat"]
            self._add_blueprint(
                sanitized_blueprints,
                ref="support_vitals",
                lane_type="support",
                title="System Vitals Check",
                prompt="Check system vitals, runtime health, and daemon readiness for the mission environment.",
                priority=96,
                depends_on=support_dependencies,
                metadata={"role": "support", "support_kind": "vitals"},
            )
            self._add_blueprint(
                sanitized_blueprints,
                ref="support_daemon",
                lane_type="support",
                title="Daemon Heartbeat Check",
                prompt="Check the proactive daemon heartbeat and monitoring pulse for the environment.",
                priority=94,
                depends_on=support_dependencies,
                metadata={"role": "support", "support_kind": "daemon_heartbeat"},
            )
            self._add_blueprint(
                sanitized_blueprints,
                ref="support_connectors",
                lane_type="support",
                title="Connector Health Sweep",
                prompt="Validate connector health and live provider connectivity across the workspace.",
                priority=92,
                depends_on=support_dependencies,
                metadata={"role": "support", "support_kind": "connector_health"},
            )

        approval_queue = sanitize_approval_queue(
            [
                item
                for item in list(planner_json.get("approval_queue") or [])
                if isinstance(item, dict)
            ],
            available_refs={str(item["ref"]) for item in sanitized_blueprints},
            execution_mode=normalized_execution_mode,
        )

        ref_to_lane_id: dict[str, str] = {}
        lanes: list[dict[str, Any]] = []
        for blueprint in sorted(
            sanitized_blueprints,
            key=lambda item: (
                -int(item.get("priority") or 0),
                len(item.get("depends_on") or []),
                item.get("ref") or "",
            ),
        ):
            lane_id = f"{blueprint['lane_type']}_{len(lanes) + 1}"
            ref_to_lane_id[blueprint["ref"]] = lane_id
            lanes.append(
                {
                    "lane_id": lane_id,
                    "lane_type": blueprint["lane_type"],
                    "title": blueprint["title"],
                    "prompt": blueprint["prompt"],
                    "parallelizable": blueprint["lane_type"] != "approval",
                    "requires_approval": blueprint["lane_type"] == "approval",
                    "depends_on": [],
                    "blocked_by": [],
                    "priority": blueprint["priority"],
                    "subagent_type": blueprint.get("subagent_type")
                    or blueprint["lane_type"],
                    "metadata": blueprint.get("metadata") or {},
                    "status": "pending",
                    "ref": blueprint["ref"],
                }
            )

        for lane in lanes:
            source_blueprint = next(
                (item for item in sanitized_blueprints if item["ref"] == lane["ref"]),
                None,
            )
            if not source_blueprint:
                continue
            lane["depends_on"] = [
                ref_to_lane_id[dep]
                for dep in source_blueprint.get("depends_on") or []
                if dep in ref_to_lane_id
            ]
            lane["blocked_by"] = [
                ref_to_lane_id[dep]
                for dep in source_blueprint.get("blocked_by") or []
                if dep in ref_to_lane_id
            ]

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
            elif lane["lane_type"] == "support":
                world = "systems"
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
                                    if lane["lane_type"] == "support"
                                    else (
                                        "amber"
                                        if lane["lane_type"] == "approval"
                                        else "slate"
                                    )
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
                        "ref": lane.get("ref"),
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
                {
                    "id": "systems",
                    "label": "System Mesh",
                    "description": "Vitals, daemon heartbeat, and connector health support checks.",
                },
            ],
        }

        parallel_limit = int(planner_json.get("parallel_limit") or 0)
        fallback_parallel_limit = max(
            2,
            min(
                len(lanes) or 2, 8 if normalized_execution_mode == "full_access" else 6
            ),
        )
        parallel_limit = max(
            2, min(parallel_limit or fallback_parallel_limit, len(lanes) or 2)
        )

        if not approval_queue and any(
            lane["lane_type"] == "approval" for lane in lanes
        ):
            approval_queue = [
                {
                    "lane_ref": lane["ref"],
                    "lane_type": "approval",
                    "message": lane["prompt"],
                    "reason": lane.get("metadata", {}).get(
                        "reason", "approval_required"
                    ),
                }
                for lane in lanes
                if lane["lane_type"] == "approval"
            ]

        return {
            "planner_source": str(planner_json.get("planner_source") or "policy"),
            "planner_mode": str(planner_json.get("planner_mode") or planner_mode),
            "planner_version": int(planner_json.get("planner_version") or 1),
            "objective": objective,
            "note_content": note_content,
            "execution_mode": normalized_execution_mode,
            "classification": planner_json.get("classification"),
            "summary": str(
                planner_json.get("summary")
                or self._summarize_planner(objective, auto_signals)
            ),
            "signals": auto_signals,
            "parallel_limit": parallel_limit,
            "approval_queue": approval_queue,
            "lane_blueprints": sanitized_blueprints,
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
                "dynamic_fanout": len(
                    [
                        lane
                        for lane in lanes
                        if lane["lane_type"] in {"research", "analysis"}
                    ]
                ),
            },
            "planner_json": planner_json,
        }
