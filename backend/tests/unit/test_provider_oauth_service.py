from __future__ import annotations

from uuid import UUID

from app.core.config import get_settings
from app.platform.database.session import get_session_factory
from app.providers.services.provider_oauth_service import ProviderOAuthService


def test_provider_oauth_service_reports_disabled_by_default() -> None:
    session = get_session_factory()()
    try:
        service = ProviderOAuthService(session, get_settings())
        available, _message = service.status(tenant_id=UUID(int=1))
        assert available is False
    finally:
        session.close()
