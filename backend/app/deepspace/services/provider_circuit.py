from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from app.system.services.cache_service import get_redis_client

logger = logging.getLogger(__name__)


class DeepSpaceProviderCircuit:
    """Redis-backed circuit state shared by DeepSpace API and workers.

    Redis unavailability is fail-open: existing provider selection continues
    instead of taking chat down because observability infrastructure failed.
    """

    PREFIX = "deepspace:provider-circuit"

    @classmethod
    def _key(
        cls, tenant_id: uuid.UUID, provider_config_id: uuid.UUID | None, model_name: str
    ) -> str:
        provider = str(provider_config_id or "builtin")
        return f"{cls.PREFIX}:{tenant_id}:{provider}:{model_name.strip().casefold()}"

    def is_open(
        self, *, tenant_id: uuid.UUID, provider_config_id: uuid.UUID | None, model_name: str
    ) -> bool:
        try:
            return bool(
                get_redis_client().get(
                    f"{self._key(tenant_id, provider_config_id, model_name)}:open"
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning("DeepSpace provider circuit read failed; failing open", exc_info=True)
            return False

    def record_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        provider_config_id: uuid.UUID | None,
        model_name: str,
        threshold: int,
        cooldown_seconds: int,
    ) -> bool:
        key = self._key(tenant_id, provider_config_id, model_name)
        try:
            client = get_redis_client()
            failures = int(cast(Any, client.incr(f"{key}:failures")))
            client.expire(f"{key}:failures", max(1, cooldown_seconds))
            if failures >= max(1, threshold):
                client.setex(f"{key}:open", max(1, cooldown_seconds), "1")
                return True
        except Exception:  # noqa: BLE001
            logger.warning("DeepSpace provider circuit write failed; failing open", exc_info=True)
        return False

    def record_success(
        self, *, tenant_id: uuid.UUID, provider_config_id: uuid.UUID | None, model_name: str
    ) -> None:
        try:
            key = self._key(tenant_id, provider_config_id, model_name)
            get_redis_client().delete(f"{key}:failures", f"{key}:open")
        except Exception:  # noqa: BLE001
            logger.warning("DeepSpace provider circuit reset failed", exc_info=True)
