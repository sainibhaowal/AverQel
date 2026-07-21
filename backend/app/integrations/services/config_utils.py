from __future__ import annotations

import json
from typing import Any


def parse_config_value(raw: Any) -> Any:
    if isinstance(raw, str):
        cleaned = raw.strip()
        if not cleaned:
            return None
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned
        return parsed
    return raw


def resolve_config_value(config: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in config:
            value = parse_config_value(config.get(key))
            if value not in (None, ""):
                return value
    return None


def resolve_config_dict(config: dict[str, Any], *keys: str) -> dict[str, Any]:
    value = resolve_config_value(config, *keys)
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        return {"token": value}
    return {}


def resolve_config_text(config: dict[str, Any], *keys: str) -> str | None:
    value = resolve_config_value(config, *keys)
    if isinstance(value, dict):
        for candidate in (
            "token",
            "access_token",
            "bot_token",
            "notion_token",
            "personal_access_token",
            "value",
        ):
            raw_value = value.get(candidate)
            if isinstance(raw_value, str) and raw_value.strip():
                return raw_value.strip()
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
