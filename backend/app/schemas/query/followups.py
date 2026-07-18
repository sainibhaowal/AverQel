from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FollowupSuggestions(BaseModel):
    follow_ups: list[str] = Field(default_factory=list, max_length=3)

    model_config = ConfigDict(extra="forbid")

    @field_validator("follow_ups")
    @classmethod
    def normalize_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()][:3]
