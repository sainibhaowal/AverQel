from __future__ import annotations

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.providers.provider_models_service import ProviderModelsService
from app.services.providers.registry import ProviderRegistry


def test_provider_models_service_initializes() -> None:
    session = get_session_factory()()
    try:
        service = ProviderModelsService(session, ProviderRegistry(get_settings()))
        assert service.configs is not None
        assert service.cache is not None
        assert service.health_checks is not None
    finally:
        session.close()
