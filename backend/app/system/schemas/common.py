from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str

    model_config = ConfigDict(extra="forbid")
