from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.services.deepspace.planning.planner_schema import (
    PlannerApprovalEntrySchema,
    PlannerLaneBlueprintSchema,
    PlannerPayloadSchema,
)

logger = logging.getLogger(__name__)

ALLOWED_LANE_TYPES = {
    "main_chat",
    "research",
    "analysis",
    "writer",
    "executor",
    "memory",
    "proactive",
    "connector",
    "support",
    "approval",
}


def parse_planner_json_payload(raw_text: str) -> Any:
    """Extract a JSON object or array from planner model output."""
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start_candidates = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
    if start_candidates:
        start = min(start_candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except Exception:
        logger.debug("Mission planner output was not valid JSON.", exc_info=True)
        return None


def validate_planner_payload(payload: Any) -> dict[str, Any] | None:
    """Validate and normalize a planner payload without changing lane semantics."""
    if not isinstance(payload, dict):
        return None
    try:
        validated = PlannerPayloadSchema.model_validate(payload)
    except ValidationError:
        logger.debug("Mission planner payload failed schema validation.", exc_info=True)
        return None

    return {
        "planner_source": validated.planner_source,
        "planner_version": validated.planner_version,
        "summary": validated.summary,
        "parallel_limit": validated.parallel_limit,
        "signals": dict(validated.signals or {}),
        "approval_queue": [
            _normalize_approval_entry(item) for item in validated.approval_queue
        ],
        "lane_blueprints": [
            _normalize_blueprint(item) for item in validated.lane_blueprints
        ],
    }


def sanitize_lane_blueprints(
    lane_blueprints: list[dict[str, Any]],
    *,
    objective: str,
    execution_mode: str,
    allowed_lane_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize planner-authored blueprints into safe materialization input."""
    normalized_execution_mode = (
        "full_access"
        if str(execution_mode).strip().lower() == "full_access"
        else "auto_review"
    )
    allowed = allowed_lane_types or ALLOWED_LANE_TYPES
    sanitized: list[dict[str, Any]] = []
    used_refs: set[str] = set()

    for index, raw_blueprint in enumerate(lane_blueprints, start=1):
        try:
            blueprint = PlannerLaneBlueprintSchema.model_validate(raw_blueprint)
        except ValidationError:
            logger.debug("Skipping invalid planner lane blueprint.", exc_info=True)
            continue

        lane_type = str(blueprint.lane_type or "").strip().lower()
        if lane_type not in allowed:
            continue
        if lane_type == "approval" and normalized_execution_mode == "full_access":
            continue

        ref = _unique_ref(
            _normalize_ref(blueprint.ref, lane_type=lane_type, index=index),
            used_refs,
        )
        depends_on = _normalize_ref_list(blueprint.depends_on)
        blocked_by = _normalize_ref_list(blueprint.blocked_by)
        if lane_type == "main_chat":
            depends_on = []
            blocked_by = []
        depends_on = [dep for dep in depends_on if dep != ref]
        blocked_by = [dep for dep in blocked_by if dep != ref]

        sanitized.append(
            {
                "ref": ref,
                "lane_type": lane_type,
                "title": str(blueprint.title or lane_type.replace("_", " ").title()),
                "prompt": str(blueprint.prompt or objective),
                "priority": int(blueprint.priority or 0),
                "depends_on": depends_on,
                "blocked_by": blocked_by,
                "subagent_type": (
                    str(blueprint.subagent_type).strip()
                    if blueprint.subagent_type is not None
                    and str(blueprint.subagent_type).strip()
                    else None
                ),
                "metadata": dict(blueprint.metadata or {}),
            }
        )

    _prune_invalid_and_cyclic_refs(sanitized)
    return sanitized


def sanitize_approval_queue(
    approval_queue: list[dict[str, Any]],
    *,
    available_refs: set[str],
    execution_mode: str,
) -> list[dict[str, Any]]:
    """Normalize approval queue entries and drop invalid references."""
    if str(execution_mode).strip().lower() == "full_access":
        return []

    normalized: list[dict[str, Any]] = []
    for raw_entry in approval_queue:
        try:
            entry = PlannerApprovalEntrySchema.model_validate(raw_entry)
        except ValidationError:
            logger.debug("Skipping invalid planner approval entry.", exc_info=True)
            continue
        lane_ref = str(entry.lane_ref or "").strip() or None
        if lane_ref is not None and lane_ref not in available_refs:
            lane_ref = None
        normalized.append(
            {
                "lane_ref": lane_ref,
                "lane_type": (str(entry.lane_type or "").strip().lower() or None),
                "message": str(entry.message or "").strip(),
                "reason": str(entry.reason or "approval_required").strip(),
            }
        )
    return [item for item in normalized if item["message"]]


def _normalize_blueprint(blueprint: PlannerLaneBlueprintSchema) -> dict[str, Any]:
    return {
        "ref": blueprint.ref,
        "lane_type": blueprint.lane_type,
        "title": blueprint.title,
        "prompt": blueprint.prompt,
        "priority": blueprint.priority,
        "depends_on": list(blueprint.depends_on),
        "blocked_by": list(blueprint.blocked_by),
        "subagent_type": blueprint.subagent_type,
        "metadata": dict(blueprint.metadata or {}),
    }


def _normalize_approval_entry(entry: PlannerApprovalEntrySchema) -> dict[str, Any]:
    return {
        "lane_ref": entry.lane_ref,
        "lane_type": entry.lane_type,
        "message": entry.message,
        "reason": entry.reason,
    }


def _normalize_ref(value: str, *, lane_type: str, index: int) -> str:
    ref = str(value or "").strip()
    if ref:
        return ref
    return f"{lane_type}_{index}"


def _unique_ref(ref: str, used_refs: set[str]) -> str:
    candidate = ref
    suffix = 2
    while candidate in used_refs:
        candidate = f"{ref}_{suffix}"
        suffix += 1
    used_refs.add(candidate)
    return candidate


def _normalize_ref_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        ref = str(value or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        normalized.append(ref)
    return normalized


def _prune_invalid_and_cyclic_refs(blueprints: list[dict[str, Any]]) -> None:
    ref_set = {str(item["ref"]) for item in blueprints}
    for blueprint in blueprints:
        blueprint["depends_on"] = [
            ref for ref in blueprint.get("depends_on") or [] if ref in ref_set
        ]
        blueprint["blocked_by"] = [
            ref for ref in blueprint.get("blocked_by") or [] if ref in ref_set
        ]

    graph = {
        str(item["ref"]): list(item.get("depends_on") or []) for item in blueprints
    }
    seen: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in seen:
            return
        seen.add(node)
        stack.append(node)
        for dep in list(graph.get(node) or []):
            if dep in stack:
                graph[node] = [item for item in graph[node] if item != dep]
                continue
            visit(dep)
        stack.pop()

    for ref in list(graph):
        visit(ref)

    for blueprint in blueprints:
        blueprint["depends_on"] = list(graph.get(str(blueprint["ref"])) or [])
