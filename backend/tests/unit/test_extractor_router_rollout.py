from __future__ import annotations

from uuid import uuid4

from app.core.config import get_settings
from app.ingestion.services.extractors.router import ExtractorRouter


def test_vision_allowlist_allows_only_configured_tenant() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    allowed = uuid4()
    blocked = uuid4()
    settings.vision_tenant_allowlist = [str(allowed)]
    router = ExtractorRouter(settings=settings)

    assert router._vision_allowed_for_tenant(allowed) is True
    assert router._vision_allowed_for_tenant(blocked) is False
    assert router._vision_allowed_for_tenant(None) is False


def test_vision_allowlist_empty_allows_all() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    settings.vision_tenant_allowlist = []
    router = ExtractorRouter(settings=settings)

    assert router._vision_allowed_for_tenant(uuid4()) is True
