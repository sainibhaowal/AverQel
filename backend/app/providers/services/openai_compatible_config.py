from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.providers.services.reasoning_capabilities import normalize_reasoning_effort_value

_PARAMETER_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_RESERVED_PARAMETER_ROOTS = {
    "model",
    "messages",
    "input",
    "stream",
    "tools",
    "tool_choice",
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
    "response_format",
    "stop",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
}
_RESERVED_AUTH_HEADERS = {
    "connection",
    "content-length",
    "content-type",
    "cookie",
    "host",
    "transfer-encoding",
}


class OpenAICompatibleReasoningSettings(BaseModel):
    """Explicit request dialect for reasoning on a custom compatible endpoint."""

    model_config = ConfigDict(extra="forbid")

    supported_efforts: list[str] = Field(default_factory=list, max_length=32)
    effort_parameter: str | None = None
    effort_values: dict[str, str] = Field(
        default_factory=lambda: {
            "low": "low",
            "medium": "medium",
            "high": "high",
            "very_high": "xhigh",
            "extreme_high": "max",
            "minimal": "minimal",
            "ultra": "ultra",
        }
    )
    effort_off_value: str | None = None
    toggle_parameter: str | None = None
    toggle_enabled_value: bool | str = True
    toggle_disabled_value: bool | str = False
    expose_response_reasoning: bool = True

    @field_validator("effort_parameter", "toggle_parameter")
    @classmethod
    def validate_parameter_path(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        root = cleaned.split(".", maxsplit=1)[0]
        if (
            len(cleaned) > 128
            or len(cleaned.split(".")) > 8
            or not _PARAMETER_PATH_RE.fullmatch(cleaned)
            or root in _RESERVED_PARAMETER_ROOTS
        ):
            raise ValueError("reasoning parameter must be a safe, non-reserved JSON field path")
        return cleaned

    @field_validator("supported_efforts")
    @classmethod
    def deduplicate_efforts(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for effort in value:
            canonical = normalize_reasoning_effort_value(effort)
            if canonical is None:
                raise ValueError("supported_efforts contains an invalid reasoning option")
            if canonical not in normalized:
                normalized.append(canonical)
        return normalized

    @field_validator("effort_values")
    @classmethod
    def validate_effort_values(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 33:
            raise ValueError("effort_values contains too many reasoning options")
        normalized: dict[str, str] = {}
        for key, item in value.items():
            canonical = normalize_reasoning_effort_value(key)
            if canonical is None:
                raise ValueError("effort_values contains an invalid reasoning option")
            if not item.strip() or len(item.strip()) > 128 or any(ord(char) < 32 for char in item):
                raise ValueError("reasoning effort values must be non-empty safe strings")
            normalized[canonical] = item.strip()
        return normalized

    @model_validator(mode="after")
    def validate_reasoning_mapping(self) -> OpenAICompatibleReasoningSettings:
        if self.supported_efforts and not self.effort_parameter:
            raise ValueError("effort_parameter is required when reasoning levels are enabled")
        missing = [effort for effort in self.supported_efforts if effort not in self.effort_values]
        if missing:
            raise ValueError("every enabled reasoning level needs an effort value")
        if self.effort_parameter and self.toggle_parameter:
            effort_path = self.effort_parameter.split(".")
            toggle_path = self.toggle_parameter.split(".")
            shared_prefix_length = min(len(effort_path), len(toggle_path))
            if effort_path[:shared_prefix_length] == toggle_path[:shared_prefix_length]:
                raise ValueError("effort and toggle fields must not overwrite each other")
        return self


class OpenAICompatibleEndpointSettings(BaseModel):
    """Validated endpoint-specific settings stored in provider metadata."""

    model_config = ConfigDict(extra="forbid")

    api_mode: Literal["chat_completions", "responses"] = "chat_completions"
    chat_completions_path: str = "/chat/completions"
    responses_path: str = "/responses"
    models_path: str | None = "/models"
    embeddings_path: str | None = "/embeddings"
    auth_header_name: str = "Authorization"
    auth_scheme: Literal["bearer", "raw"] = "bearer"
    stream_usage: Literal["auto", "enabled", "disabled"] = "auto"
    max_tokens_parameter: (
        Literal["max_tokens", "max_completion_tokens", "max_output_tokens"] | None
    ) = None
    send_max_tokens: bool = True
    send_temperature: bool = True
    send_embedding_dimensions: bool = False
    reasoning: OpenAICompatibleReasoningSettings = Field(
        default_factory=OpenAICompatibleReasoningSettings
    )

    @field_validator("chat_completions_path", "responses_path", "models_path", "embeddings_path")
    @classmethod
    def validate_endpoint_path(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if (
            not cleaned.startswith("/")
            or "?" in cleaned
            or "#" in cleaned
            or "\\" in cleaned
            or any(segment == ".." for segment in cleaned.split("/"))
            or len(cleaned) > 512
        ):
            raise ValueError("endpoint paths must be absolute URL paths without query or traversal")
        if (
            not re.fullmatch(r"/[A-Za-z0-9._~{}:/-]*", cleaned)
            or cleaned.count("{model}") > 1
            or "{" in cleaned.replace("{model}", "")
            or "}" in cleaned.replace("{model}", "")
        ):
            raise ValueError("endpoint path contains unsupported characters")
        return cleaned.rstrip("/") or "/"

    @field_validator("auth_header_name")
    @classmethod
    def validate_auth_header_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not _HEADER_NAME_RE.fullmatch(cleaned) or cleaned.lower() in _RESERVED_AUTH_HEADERS:
            raise ValueError("auth_header_name must be a valid HTTP header name")
        return cleaned

    @model_validator(mode="after")
    def validate_models_route(self) -> OpenAICompatibleEndpointSettings:
        if self.models_path and "{model}" in self.models_path:
            raise ValueError("models_path cannot contain a model placeholder")
        return self


def openai_compatible_settings(
    metadata: object, *, provider_type: str | None = None
) -> OpenAICompatibleEndpointSettings:
    """Resolve a provider's documented routes and custom endpoint settings."""
    provider = (provider_type or "custom").strip().lower()
    defaults: dict[str, Any] = {}
    if provider == "cline":
        # Cline exposes a public OpenAI-style model catalog, but no
        # embeddings route. Keep the shared /models default and disable only
        # embeddings for this provider.
        defaults.update(embeddings_path=None)
    elif provider == "moonshot":
        # Kimi documents authenticated model discovery and chat completion,
        # but its API reference does not expose an embeddings route.
        defaults.update(embeddings_path=None)
    elif provider == "zai":
        # Z.AI documents Chat Completions but no OpenAI-compatible model list
        # or embeddings route. Model IDs are entered explicitly in the form.
        defaults.update(models_path=None, embeddings_path=None)
    elif provider == "meta":
        # Meta's Model API lists models, while its hosted Model API does not
        # document an embeddings endpoint. Responses is the recommended
        # interface for tool-using agent workloads.
        defaults.update(api_mode="responses", embeddings_path=None, send_temperature=False)

    raw: dict[str, Any] = {}
    if provider == "custom":
        if isinstance(metadata, dict):
            configured = metadata.get("openai_compatible", {})
            if not isinstance(configured, dict):
                raise ValueError("metadata_json.openai_compatible must be an object")
            raw = configured
    return OpenAICompatibleEndpointSettings.model_validate({**defaults, **raw})


def provider_model_listing_enabled(provider_type: str, configured: bool) -> bool:
    """Return the effective listing capability, including for legacy Cline rows."""
    return bool(configured) or provider_type.strip().lower() == "cline"


def reasoning_efforts_from_metadata(metadata: object) -> list[str]:
    settings = openai_compatible_settings(metadata)
    return list(settings.reasoning.supported_efforts)


def set_json_path(payload: dict[str, Any], path: str, value: Any) -> None:
    """Set a validated dotted JSON path, replacing non-object intermediates."""
    segments = path.split(".")
    cursor = payload
    for segment in segments[:-1]:
        child = cursor.get(segment)
        if not isinstance(child, dict):
            child = {}
            cursor[segment] = child
        cursor = child
    cursor[segments[-1]] = value
