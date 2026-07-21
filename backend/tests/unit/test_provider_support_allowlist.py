from __future__ import annotations

from app.db.session import get_session_factory
from app.providers.services.provider_management_service import ProviderManagementService


def test_provider_support_catalog_keeps_account_linking_disabled_by_default() -> None:
    session = get_session_factory()()
    try:
        service = ProviderManagementService(session)
        catalog = {
            item["provider_type"]: item for item in service.list_supported_types()
        }
        assert catalog["openai"]["supports_account_linking"] is False
        assert catalog["ollama"]["supports_account_linking"] is False
        assert catalog["lmstudio"]["supports_account_linking"] is False
        assert catalog["opencode-zen"]["supports_account_linking"] is False
        assert catalog["opencode-zen"]["supports_chat"] is True
        assert catalog["tavily"]["supports_web_search"] is True
        assert catalog["tavily"]["supports_chat"] is False
    finally:
        session.close()
