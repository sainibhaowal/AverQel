from __future__ import annotations

import re
from typing import Any

from app.providers.services.reasoning_capabilities import normalize_reasoning_effort_value

CODEX_ACCOUNT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
CODEX_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_./:-]{1,255}$")
CODEX_NATIVE_EFFORT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,19}$")


def codex_supported_reasoning_efforts(settings: object, model_name: str) -> tuple[str, ...] | None:
    """Return account-catalog reasoning values for one model, preserving unknown vs empty."""
    if not isinstance(settings, dict):
        return None
    models = settings.get("models")
    if not isinstance(models, list):
        return None
    for item in models:
        if not isinstance(item, dict) or item.get("id") != model_name:
            continue
        efforts = item.get("supported_reasoning_efforts")
        if not isinstance(efforts, list):
            return None
        normalized: list[str] = []
        for effort in efforts:
            value = normalize_reasoning_effort_value(effort)
            if value and value not in normalized:
                normalized.append(value)
        return tuple(normalized)
    return None


def codex_reasoning_effort_values(settings: object, model_name: str) -> dict[str, str] | None:
    """Return the exact native effort token advertised for a selected model."""
    if not isinstance(settings, dict):
        return None
    models = settings.get("models")
    if not isinstance(models, list):
        return None
    for item in models:
        if not isinstance(item, dict) or item.get("id") != model_name:
            continue
        values = item.get("reasoning_effort_values")
        if isinstance(values, dict):
            return {
                effort: native
                for effort, native in values.items()
                if isinstance(effort, str)
                and isinstance(native, str)
                and normalize_reasoning_effort_value(effort) == effort
                and CODEX_NATIVE_EFFORT_PATTERN.fullmatch(native)
            }
        efforts = item.get("supported_reasoning_efforts")
        if isinstance(efforts, list):
            return {
                canonical: native
                for effort in efforts
                if isinstance(effort, str)
                and (canonical := normalize_reasoning_effort_value(effort)) is not None
                and (native := effort.strip())
            }
        return None
    return None


def validate_codex_desktop_settings(
    metadata: dict[str, Any], *, default_chat_model: str | None = None
) -> dict[str, Any]:
    settings = metadata.get("codex_desktop")
    if not isinstance(settings, dict):
        raise ValueError("Codex login requires local account and model metadata.")
    if set(settings) - {"account_id", "models"}:
        raise ValueError("Codex provider metadata contains unsupported fields.")
    account_id = settings.get("account_id")
    if not isinstance(account_id, str) or not CODEX_ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise ValueError("Codex account identifier is invalid.")
    models = settings.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= 500:
        raise ValueError("Codex provider needs a current account model list.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict) or set(item) - {
            "id",
            "name",
            "kind",
            "supported_reasoning_efforts",
            "reasoning_effort_values",
        }:
            raise ValueError("Codex model entries contain unsupported fields.")
        model_id = item.get("id")
        display_name = item.get("name")
        if (
            not isinstance(model_id, str)
            or not CODEX_MODEL_ID_PATTERN.fullmatch(model_id)
            or not isinstance(display_name, str)
            or not display_name.strip()
            or len(display_name) > 255
            or ("kind" in item and item["kind"] != "chat")
        ):
            raise ValueError("Codex model entry is invalid.")
        reasoning_efforts = item.get("supported_reasoning_efforts")
        if "supported_reasoning_efforts" in item and (
            not isinstance(reasoning_efforts, list)
            or len(reasoning_efforts) > 32
            or any(
                not isinstance(effort, str) or normalize_reasoning_effort_value(effort) is None
                for effort in reasoning_efforts
            )
        ):
            raise ValueError("Codex model reasoning metadata is invalid.")
        if model_id in seen:
            continue
        seen.add(model_id)
        normalized_item: dict[str, Any] = {"id": model_id, "name": display_name.strip()}
        if "supported_reasoning_efforts" in item:
            normalized_efforts: list[str] = []
            native_values: dict[str, str] = {}
            for effort in reasoning_efforts if isinstance(reasoning_efforts, list) else []:
                canonical = normalize_reasoning_effort_value(effort)
                if canonical and canonical not in normalized_efforts:
                    normalized_efforts.append(canonical)
                    native_values[canonical] = effort.strip()
            supplied_values = item.get("reasoning_effort_values")
            if supplied_values is not None:
                if (
                    not isinstance(supplied_values, dict)
                    or len(supplied_values) > 32
                    or any(
                        not isinstance(name, str)
                        or normalize_reasoning_effort_value(name) not in normalized_efforts
                        or not isinstance(native, str)
                        or not CODEX_NATIVE_EFFORT_PATTERN.fullmatch(native)
                        for name, native in supplied_values.items()
                    )
                ):
                    raise ValueError("Codex model reasoning metadata is invalid.")
                for name, native in supplied_values.items():
                    canonical = normalize_reasoning_effort_value(name)
                    if canonical:
                        native_values[canonical] = native
            normalized_item["supported_reasoning_efforts"] = normalized_efforts
            normalized_item["reasoning_effort_values"] = native_values
        normalized.append(normalized_item)
    if not normalized:
        raise ValueError("Codex provider needs at least one available chat model.")
    if default_chat_model and default_chat_model not in seen:
        raise ValueError("The selected Codex model is not available for this account.")
    return {"account_id": account_id, "models": normalized}
