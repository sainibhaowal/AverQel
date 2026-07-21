"""Schemas for collection expiry operations."""

from pydantic import BaseModel, ConfigDict


class UpdateExpiryPayload(BaseModel):
    expiry_days: int

    model_config = ConfigDict(extra="forbid")
