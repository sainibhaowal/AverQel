from __future__ import annotations

from typing import Any
from uuid import UUID

from app.providers.services.types import ProviderSelectionCandidate
from app.query.schemas.followups import FollowupSuggestions
from app.query.services.answer_service import AnswerService


class FollowupService:
    def __init__(self, answer_service: AnswerService) -> None:
        self.answer_service = answer_service

    def generate(
        self,
        *,
        query_text: str,
        answer_text: str,
        tenant_id: UUID,
        previous_messages: list[dict[str, str]] | None = None,
        provider_candidates: list[ProviderSelectionCandidate] | None = None,
    ) -> FollowupSuggestions:
        return FollowupSuggestions(
            follow_ups=self.answer_service.generate_followups(
                query_text=query_text,
                answer_text=answer_text,
                tenant_id=tenant_id,
                previous_messages=previous_messages,
                provider_candidates=provider_candidates,
            )
        )

    @staticmethod
    def as_metadata(items: FollowupSuggestions | list[str]) -> dict[str, Any]:
        payload = (
            items
            if isinstance(items, FollowupSuggestions)
            else FollowupSuggestions(follow_ups=items)
        )
        return {"follow_up_suggestions": payload.follow_ups}
