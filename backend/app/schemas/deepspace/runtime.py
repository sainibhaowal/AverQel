"""Schemas for DeepSpace execution preferences and approvals."""

import uuid
from typing import Literal

from pydantic import BaseModel


class UpdateExecutionModeRequest(BaseModel):
    execution_mode: Literal["auto_review", "full_access"]
    conversation_id: uuid.UUID | None = None


class UpdateRuntimePreferencesRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    execution_mode: Literal["auto_review", "full_access"] | None = None
    planner_mode: Literal["default", "structured"] | None = None
    subagent_profile: (
        Literal[
            "default",
            "research",
            "analysis",
            "writer",
            "executor",
            "planner",
            "support",
            "file",
        ]
        | None
    ) = None
    runtime_hooks_enabled: bool | None = None
    workspace_mode_enabled: bool | None = None
    full_autonomy_enabled: bool | None = None


class ResolveMissionApprovalRequest(BaseModel):
    lane_id: str
    approved: bool = True
