from __future__ import annotations

import pytest

from app.providers.services.registry import (
    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES,
    OPENAI_COMPATIBLE_PROVIDER_TYPES,
    ProviderRegistry,
)

pytestmark = pytest.mark.unit_no_db


CHAT_PROVIDER_TYPES = tuple(
    sorted(
        {
            *OPENAI_COMPATIBLE_PROVIDER_TYPES,
            "anthropic",
            "google",
            "lmstudio",
            "manus",
            "ollama",
            "opencode-zen",
            "openrouter",
        }
    )
)
EMBEDDING_PROVIDER_TYPES = tuple(
    sorted(
        {
            *OPENAI_COMPATIBLE_EMBEDDING_PROVIDER_TYPES,
            "lmstudio",
            "local-deterministic",
            "ollama",
            "openrouter",
            "sentence-transformers",
        }
    )
)


@pytest.mark.parametrize("provider_type", CHAT_PROVIDER_TYPES)
def test_every_supported_chat_provider_binds_without_network(provider_type: str) -> None:
    provider = ProviderRegistry._bind_chat_provider(
        provider_type,
        base_url="https://provider-contract.invalid/v1",
        api_key="contract-test-key",
        metadata={},
    )
    assert callable(getattr(provider, "generate", None))


@pytest.mark.parametrize("provider_type", EMBEDDING_PROVIDER_TYPES)
def test_every_supported_embedding_provider_binds_without_network(
    provider_type: str,
) -> None:
    provider = ProviderRegistry._bind_embedding_provider(
        provider_type,
        base_url="https://provider-contract.invalid/v1",
        api_key="contract-test-key",
        metadata={},
    )
    assert callable(getattr(provider, "embed_many", None))
