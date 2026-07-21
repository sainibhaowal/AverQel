from __future__ import annotations

from typing import Any

from app.providers.services.base import ProviderRequestError
from app.providers.services.openai_compatible import OpenAICompatibleProvider
from app.providers.services.url_resolution import resolve_provider_base_url


class OpenRouterProvider(OpenAICompatibleProvider):
    provider_name = "openrouter"

    def __init__(
        self,
        *,
        supports_embeddings: bool = False,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            supports_embeddings=supports_embeddings,
            base_url=base_url or "https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def bind(self, base_url: str, api_key: str | None = None) -> OpenRouterProvider:
        self.base_url = (
            resolve_provider_base_url(base_url) or "https://openrouter.ai/api/v1"
        )
        self.api_key = api_key
        return self

    @staticmethod
    def _build_headers(api_key: str | None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://averqel.ai",
            "X-Title": "AverQel",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @classmethod
    def _raise_provider_error(
        cls,
        response: Any,
        *,
        payload: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> None:
        if payload is None and text is None:
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                payload = None
            try:
                response_text = getattr(response, "text", None)
            except Exception:  # noqa: BLE001
                response_text = None
            if isinstance(response_text, str):
                text = response_text
        raise ProviderRequestError(
            provider_name="openrouter",
            status_code=int(response.status_code),
            message=cls._extract_provider_error_message(payload=payload, text=text),
        )
