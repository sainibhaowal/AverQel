"""Compatibility import for the provider-owned secret service."""

from app.providers.services.provider_secret_service import (
    MaskedProviderSecret,
    ProviderSecretService,
)

__all__ = ["MaskedProviderSecret", "ProviderSecretService"]
