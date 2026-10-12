from __future__ import annotations

import pytest

from app.providers.services.provider_management_service import SUPPORTED_PROVIDER_CATALOG
from app.providers.services.registry import (
    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES,
    OPENAI_COMPATIBLE_PROVIDER_TYPES,
)

pytestmark = pytest.mark.unit_no_db


def test_mistral_meta_and_cline_catalog_capabilities_match_their_routes() -> None:
    assert SUPPORTED_PROVIDER_CATALOG["mistral"] == {
        "display_name": "Mistral AI",
        "auth_modes": ["api_key"],
        "supports_chat": True,
        "supports_embeddings": True,
        "supports_reranking": False,
        "supports_web_search": False,
        "supports_model_listing": True,
        "supports_model_install": False,
        "supports_account_linking": False,
        "is_local": False,
    }
    assert SUPPORTED_PROVIDER_CATALOG["meta"]["supports_chat"] is True
    assert SUPPORTED_PROVIDER_CATALOG["meta"]["supports_embeddings"] is False
    assert SUPPORTED_PROVIDER_CATALOG["meta"]["supports_model_listing"] is True
    assert SUPPORTED_PROVIDER_CATALOG["cline"]["supports_chat"] is True
    assert SUPPORTED_PROVIDER_CATALOG["cline"]["supports_embeddings"] is False
    assert SUPPORTED_PROVIDER_CATALOG["cline"]["supports_model_listing"] is True
    assert all(
        SUPPORTED_PROVIDER_CATALOG[provider]["supports_account_linking"] is False
        for provider in ("mistral", "meta", "cline")
    )


def test_only_embedding_capable_new_provider_is_registered_for_embeddings() -> None:
    assert {"mistral", "meta", "cline"}.issubset(OPENAI_COMPATIBLE_PROVIDER_TYPES)
    assert "mistral" in OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES
    assert "meta" not in OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES
    assert "cline" not in OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES
