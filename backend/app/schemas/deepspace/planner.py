"""Schemas for validated DeepSpace planner payloads."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlannerLaneBlueprintSchema(BaseModel):
    """Validated shape for a planner-authored lane blueprint."""

    model_config = ConfigDict(extra="ignore")

    ref: str
    lane_type: str
    title: str
    prompt: str
    priority: int = 0
    depends_on: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    subagent_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerApprovalEntrySchema(BaseModel):
    """Validated shape for planner approval queue entries."""

    model_config = ConfigDict(extra="ignore")

    lane_ref: str | None = None
    lane_type: str | None = None
    message: str
    reason: str | None = None


class PlannerPayloadSchema(BaseModel):
    """Validated top-level planner payload shape."""

    model_config = ConfigDict(extra="ignore")

    planner_source: str | None = None
    planner_version: int | None = None
    summary: str | None = None
    parallel_limit: int | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    approval_queue: list[PlannerApprovalEntrySchema] = Field(default_factory=list)
    lane_blueprints: list[PlannerLaneBlueprintSchema] = Field(default_factory=list)
