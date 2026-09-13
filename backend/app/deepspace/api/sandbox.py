"""Authenticated entry point for isolated Python/SQL execution."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import AuthContext, get_auth_context
from app.auth.rbac import require_permissions
from app.core.config import Settings, get_settings
from app.deepspace.services.sandbox_executor import SandboxExecutorError, execute_sandbox

router = APIRouter(prefix="/deepspace/sandbox", tags=["deepspace-sandbox"])


class SandboxExecuteRequest(BaseModel):
    language: str = Field(pattern="^(python|sql)$")
    code: str = Field(min_length=1, max_length=100_000)
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=20, ge=1, le=30)


@router.post(
    "/execute",
    dependencies=[Depends(require_permissions("queries:run"))],
)
async def execute(
    payload: SandboxExecuteRequest,
    _auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Execute only in the separately isolated service; never in this API process."""
    try:
        return await execute_sandbox(
            code=payload.code,
            language=payload.language,
            settings=settings,
            input_data=payload.input,
            timeout_seconds=payload.timeout_seconds,
        )
    except SandboxExecutorError as exc:
        return {"status": "unavailable", "execution": "isolated_sandbox", "message": str(exc)}
