from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.services.deepspace.subagents.subagent_profiles import SubagentProfile


@dataclass(frozen=True, slots=True)
class SubagentExecutionContext:
    user_message: str
    thinking_enabled: bool
    web_search_enabled: bool
    metadata: dict[str, str]


def build_subagent_context(
    *,
    profile: SubagentProfile,
    prompt: str,
    execution_mode: str,
    parent_id: uuid.UUID,
) -> SubagentExecutionContext:
    normalized_prompt = str(prompt or "").strip()
    normalized_mode = (
        "full_access"
        if str(execution_mode).strip().lower() == "full_access"
        else "auto_review"
    )

    packaged_prompt = (
        f"SUBAGENT PROFILE: {profile.display_name}\n"
        f"REQUESTED TYPE: {profile.requested_type}\n"
        f"CANONICAL TYPE: {profile.canonical_type}\n"
        f"EXECUTION MODE: {normalized_mode}\n"
        f"PARENT LINEAGE ID: {parent_id}\n\n"
        "MISSION:\n"
        f"{normalized_prompt}\n\n"
        "ROLE GOAL:\n"
        f"{profile.goal}\n\n"
        "OUTPUT REQUIREMENTS:\n"
        f"{profile.output_contract}\n"
        "- Keep the response concise, high-signal, and action-oriented.\n"
        "- Do not reveal internal chain-of-thought.\n"
        "- If blocked, say exactly what is missing.\n"
    )

    return SubagentExecutionContext(
        user_message=packaged_prompt,
        thinking_enabled=profile.thinking_enabled,
        web_search_enabled=profile.web_search_enabled,
        metadata={
            "requested_type": profile.requested_type,
            "canonical_type": profile.canonical_type,
            "display_name": profile.display_name,
            "execution_mode": normalized_mode,
            "parent_id": str(parent_id),
        },
    )
