from app.services.security.provider_secret_crypto import (
    EncryptedProviderSecret,
    ProviderSecretCrypto,
    ProviderSecretCryptoError,
)
__all__ = [
    "EncryptedProviderSecret",
    "MaskedProviderSecret",
    "ProviderSecretCrypto",
    "ProviderSecretCryptoError",
    "ProviderSecretService",
]


def __getattr__(name: str):
    """Load the provider-owned service without creating an import cycle."""
    if name in {"MaskedProviderSecret", "ProviderSecretService"}:
        from app.providers.services.provider_secret_service import (
            MaskedProviderSecret,
            ProviderSecretService,
        )

        return {
            "MaskedProviderSecret": MaskedProviderSecret,
            "ProviderSecretService": ProviderSecretService,
        }[name]
    raise AttributeError(name)
