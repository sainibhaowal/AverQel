from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.providers.models.provider_health_check import ProviderHealthCheck
from app.providers.services.provider_models_service import ProviderModelsService
from app.providers.services.registry import ProviderRegistry


@dataclass(slots=True)
class ProviderHealthService:
    db: Session
    registry: ProviderRegistry

    def test_and_record(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> ProviderHealthCheck:
        return ProviderModelsService(self.db, self.registry).test_provider(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
            actor_user_id=actor_user_id,
        )

    def latest(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID,
    ) -> ProviderHealthCheck | None:
        return ProviderModelsService(self.db, self.registry).get_latest_health(
            tenant_id=tenant_id,
            provider_config_id=provider_config_id,
        )
