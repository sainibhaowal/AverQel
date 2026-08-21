from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    version: str | None = None
    git_sha: str | None = None
    build_timestamp_utc: str | None = None

    model_config = ConfigDict(extra="forbid")
