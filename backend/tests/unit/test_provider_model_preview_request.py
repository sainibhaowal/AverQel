from __future__ import annotations

from app.providers.schemas.models import ProviderModelPreviewRequest


def test_provider_model_preview_request_strips_invisible_characters_from_url() -> None:
    payload = ProviderModelPreviewRequest.model_validate(
        {
            "provider_type": "lmstudio",
            "api_base_url": "http://host.docker.internal:1234/v1\ufeff",
            "auth_mode": "local_no_key",
            "supports_model_listing": True,
        }
    )

    assert payload.api_base_url == "http://host.docker.internal:1234/v1"
