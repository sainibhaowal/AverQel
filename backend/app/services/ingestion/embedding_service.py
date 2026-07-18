from __future__ import annotations

import hashlib
import logging
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import Settings
from app.core.errors import ApiError
from app.services.providers import EmbeddingRequest, ProviderRegistry
from app.services.providers.selection_service import ProviderSelectionService
from app.services.system.metrics_service import (
    EMBEDDING_PROVIDER_FAILURES_TOTAL,
    EMBEDDING_PROVIDER_LATENCY_SECONDS,
)

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017
logger = logging.getLogger(__name__)


class RetryableEmbeddingError(Exception):
    pass


class NonRetryableEmbeddingError(Exception):
    pass


class EmbeddingProviderNotConfiguredError(NonRetryableEmbeddingError):
    pass


@dataclass(slots=True)
class CircuitState:
    failures: int = 0
    opened_until: datetime | None = None


@dataclass(slots=True, frozen=True)
class EmbeddingRunMetadata:
    provider: str
    model: str
    provider_config_id: uuid.UUID | None = None
    source: str = "env_fallback"
    fallback_used: bool = False
    failure_code: str | None = None
    failure_message_redacted: str | None = None


@dataclass(slots=True, frozen=True)
class EmbeddingRunResult:
    vectors: list[list[float]]
    metadata: EmbeddingRunMetadata


class EmbeddingService:
    _state = CircuitState()

    def __init__(self, settings: Settings, db: Session | None = None) -> None:
        self.settings = settings
        self.db = db
        self._last_run_metadata: EmbeddingRunMetadata | None = None
        self._last_failure_context: dict[str, Any] | None = None

    def embed_many(
        self,
        texts: list[str],
        *,
        tenant_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[list[float]]:
        self._last_run_metadata = None
        self._last_failure_context = None
        try:
            self._guard_circuit_state()
            try:
                return self._embed_with_retry(
                    texts,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_user_id=actor_user_id,
                )
            except TypeError as exc:
                if not any(
                    token in str(exc)
                    for token in ("tenant_id", "workspace_id", "actor_user_id")
                ):
                    raise
                # Preserve compatibility with older test doubles patched against
                # the legacy _embed_with_retry(texts) signature.
                return self._embed_with_retry(texts)
        except RetryError as exc:
            self._record_failure()
            EMBEDDING_PROVIDER_FAILURES_TOTAL.labels(reason="retry_exhausted").inc()
            raise ApiError(
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
                message="Embedding provider is unavailable after retries.",
                status_code=503,
                details=self._last_failure_context or {},
            ) from exc
        except EmbeddingProviderNotConfiguredError as exc:
            raise ApiError(
                code="EMBEDDING_PROVIDER_NOT_CONFIGURED",
                message="No embedding provider is configured in Provider Settings.",
                status_code=400,
                details=self._last_failure_context or {},
            ) from exc
        except NonRetryableEmbeddingError as exc:
            EMBEDDING_PROVIDER_FAILURES_TOTAL.labels(reason="non_retryable").inc()
            if self.settings.embedding_provider != "local-deterministic":
                logger.warning(
                    "embedding provider failed with non-retryable error; falling back to local deterministic embeddings"
                )
                vectors = self._embed_with_local_fallback(texts)
                self._last_run_metadata = EmbeddingRunMetadata(
                    provider="local-fallback",
                    model="hash-fallback",
                    source="env_fallback",
                    fallback_used=True,
                    failure_code="EMBEDDING_REQUEST_INVALID",
                    failure_message_redacted="Embedding request was invalid.",
                )
                return vectors
            raise ApiError(
                code="EMBEDDING_REQUEST_INVALID",
                message="Embedding request was invalid.",
                status_code=422,
                details=self._last_failure_context or {},
            ) from exc
        except RetryableEmbeddingError as exc:
            self._record_failure()
            EMBEDDING_PROVIDER_FAILURES_TOTAL.labels(reason="retryable").inc()
            if self.settings.embedding_provider != "local-deterministic":
                logger.warning(
                    "embedding provider failed with retryable error; falling back to local deterministic embeddings"
                )
                vectors = self._embed_with_local_fallback(texts)
                self._last_run_metadata = EmbeddingRunMetadata(
                    provider="local-fallback",
                    model="hash-fallback",
                    source="env_fallback",
                    fallback_used=True,
                    failure_code="EMBEDDING_PROVIDER_UNAVAILABLE",
                    failure_message_redacted="Embedding provider request failed.",
                )
                return vectors
            raise ApiError(
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
                message="Embedding provider request failed.",
                status_code=503,
                details=self._last_failure_context or {},
            ) from exc
        except ApiError as exc:
            if (
                exc.code == "PROVIDER_CIRCUIT_OPEN"
                and self.settings.embedding_provider != "local-deterministic"
            ):
                logger.warning(
                    "embedding provider circuit is open; falling back to local deterministic embeddings"
                )
                vectors = self._embed_with_local_fallback(texts)
                self._last_run_metadata = EmbeddingRunMetadata(
                    provider="local-fallback",
                    model="hash-fallback",
                    source="env_fallback",
                    fallback_used=True,
                    failure_code="PROVIDER_CIRCUIT_OPEN",
                    failure_message_redacted="Embedding provider circuit breaker is open.",
                )
                return vectors
            raise
        except Exception as exc:  # noqa: BLE001
            self._record_failure()
            EMBEDDING_PROVIDER_FAILURES_TOTAL.labels(reason="unexpected").inc()
            raise ApiError(
                code="EMBEDDING_PROVIDER_UNAVAILABLE",
                message="Embedding provider request failed unexpectedly.",
                status_code=503,
                details=self._last_failure_context or {},
            ) from exc

    def embed_many_with_metadata(
        self,
        texts: list[str],
        *,
        tenant_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> EmbeddingRunResult:
        vectors = self.embed_many(
            texts,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        metadata = self._last_run_metadata or EmbeddingRunMetadata(
            provider=self.settings.embedding_provider,
            model=self.settings.embedding_model,
            source="env_fallback",
        )
        return EmbeddingRunResult(vectors=vectors, metadata=metadata)

    def _embed_with_retry(
        self,
        texts: list[str],
        *,
        tenant_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[list[float]]:
        retryer = Retrying(
            retry=retry_if_exception_type(RetryableEmbeddingError),
            stop=stop_after_attempt(self.settings.provider_retry_attempts),
            wait=wait_exponential_jitter(initial=1, max=8),
            reraise=True,
        )
        for attempt in retryer:
            with attempt:
                return self._embed_provider_call(
                    texts,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_user_id=actor_user_id,
                )
        raise ApiError(
            code="EMBEDDING_PROVIDER_UNAVAILABLE",
            message="Embedding provider retry policy exhausted.",
            status_code=503,
        )

    def _embed_with_local_fallback(self, texts: list[str]) -> list[list[float]]:
        start = time.monotonic()
        vectors = [self._deterministic_vector(text) for text in texts]
        EMBEDDING_PROVIDER_LATENCY_SECONDS.labels(
            provider="local-fallback",
            model="hash-fallback",
        ).observe(time.monotonic() - start)
        return vectors

    def _deterministic_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for idx in range(self.settings.embedding_dimension):
            start = (idx * 4) % len(digest)
            chunk = digest[start : start + 4]
            integer_value = struct.unpack("!I", chunk)[0]
            normalized = (integer_value / 2**32) * 2 - 1
            values.append(round(normalized, 7))
        return values

    def _embed_provider_call(
        self,
        texts: list[str],
        *,
        tenant_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[list[float]]:
        start = time.monotonic()
        for text in texts:
            if "__EMBED_NONRETRYABLE__" in text:
                raise NonRetryableEmbeddingError("non-retryable embedding input")
            if "__EMBED_RETRYABLE__" in text:
                raise RetryableEmbeddingError("retryable provider failure")
            if "__EMBED_TIMEOUT__" in text:
                raise RetryableEmbeddingError("provider timeout exceeded")

        selection_candidates = None
        if self.db is not None and tenant_id is not None:
            selection_candidates = (
                ProviderSelectionService(self.db, self.settings)
                .resolve_embeddings(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_user_id=actor_user_id,
                )
                .candidates
            )
            # If no candidates are found in DB, we fall through to the env-based fallback logic.

        if selection_candidates:
            last_message = "embedding provider request failed"
            last_non_retryable = False
            for candidate in selection_candidates:
                provider = ProviderRegistry(
                    self.settings
                ).get_embedding_provider_from_selection(candidate)
                try:
                    response = provider.embed_many(
                        EmbeddingRequest(
                            texts=texts,
                            model=candidate.model_name,
                            batch_size=self.settings.embedding_batch_size,
                            normalize=self.settings.embedding_normalize,
                            dimension=self.settings.embedding_dimension,
                            timeout_seconds=self.settings.embedding_timeout_seconds,
                            provider_name=candidate.provider_type,
                            metadata={
                                "base_url": candidate.base_url,
                                "api_key": candidate.api_key,
                            },
                        )
                    )
                    vectors = self._validate_vectors(
                        response.vectors,
                        dimension=self.settings.embedding_dimension,
                    )
                    self._record_success()
                    EMBEDDING_PROVIDER_LATENCY_SECONDS.labels(
                        provider=candidate.provider_type,
                        model=candidate.model_name,
                    ).observe(time.monotonic() - start)
                    self._last_run_metadata = EmbeddingRunMetadata(
                        provider=candidate.provider_type,
                        model=candidate.model_name,
                        provider_config_id=candidate.provider_config_id,
                        source=candidate.source,
                        fallback_used=candidate.source
                        in {"workspace_fallback", "tenant_fallback"},
                    )
                    return vectors
                except RuntimeError as exc:
                    message = str(exc)
                    last_message = message
                    self._last_failure_context = self._build_failure_context(
                        provider_type=candidate.provider_type,
                        model_name=candidate.model_name,
                        source=candidate.source,
                        reason=message,
                    )
                    if (
                        "dimension mismatch" in message.lower()
                        or "non-retryable" in message.lower()
                    ):
                        last_non_retryable = True
                        continue
                    continue
            # Database provider assignments are allowed to fail over to the
            # server/env embedding route rather than hard-failing retrieval.
            if not last_non_retryable:
                raise RetryableEmbeddingError(last_message)

        if self.settings.embedding_provider == "sentence-transformers":
            provider = ProviderRegistry(self.settings).get_embedding_provider(
                "sentence-transformers"
            )
            try:
                response = provider.embed_many(
                    EmbeddingRequest(
                        texts=texts,
                        model=self.settings.embedding_model,
                        batch_size=self.settings.embedding_batch_size,
                        normalize=self.settings.embedding_normalize,
                        dimension=self.settings.embedding_dimension,
                        timeout_seconds=self.settings.embedding_timeout_seconds,
                        provider_name=self.settings.embedding_provider,
                        metadata={},
                    )
                )
                vectors = self._validate_vectors(
                    response.vectors,
                    dimension=self.settings.embedding_dimension,
                )
            except RuntimeError as exc:
                message = str(exc)
                self._last_failure_context = self._build_failure_context(
                    provider_type=self.settings.embedding_provider,
                    model_name=self.settings.embedding_model,
                    source="env_fallback",
                    reason=message,
                )
                if "dimension mismatch" in message.lower():
                    raise NonRetryableEmbeddingError(message) from exc
                raise RetryableEmbeddingError(message) from exc
            self._record_success()
            EMBEDDING_PROVIDER_LATENCY_SECONDS.labels(
                provider=self.settings.embedding_provider,
                model=self.settings.embedding_model,
            ).observe(time.monotonic() - start)
            self._last_run_metadata = EmbeddingRunMetadata(
                provider=self.settings.embedding_provider,
                model=self.settings.embedding_model,
                source="env_fallback",
            )
            return vectors
        if self.settings.embedding_provider == "local-deterministic":
            vectors = [self._deterministic_vector(text) for text in texts]
            elapsed = time.monotonic() - start
            if elapsed > float(self.settings.provider_timeout_seconds):
                raise RetryableEmbeddingError("provider timeout exceeded")
            EMBEDDING_PROVIDER_LATENCY_SECONDS.labels(
                provider="local-deterministic",
                model=self.settings.embedding_model,
            ).observe(elapsed)
            self._record_success()
            self._last_run_metadata = EmbeddingRunMetadata(
                provider="local-deterministic",
                model=self.settings.embedding_model,
                source="env_fallback",
            )
            return vectors

        provider = ProviderRegistry(self.settings).get_embedding_provider()
        try:
            response = provider.embed_many(
                EmbeddingRequest(
                    texts=texts,
                    model=self.settings.embedding_model,
                    batch_size=self.settings.embedding_batch_size,
                    normalize=self.settings.embedding_normalize,
                    dimension=self.settings.embedding_dimension,
                    timeout_seconds=self.settings.embedding_timeout_seconds,
                    provider_name=self.settings.embedding_provider,
                    metadata={
                        "base_url": self.settings.llm_api_base_url,
                        "api_key": self.settings.llm_api_key,
                    },
                )
            )
            vectors = self._validate_vectors(
                response.vectors,
                dimension=self.settings.embedding_dimension,
            )
        except RuntimeError as exc:
            message = str(exc)
            self._last_failure_context = self._build_failure_context(
                provider_type=self.settings.embedding_provider,
                model_name=self.settings.embedding_model,
                source="env_fallback",
                reason=message,
            )
            if "dimension mismatch" in message.lower():
                raise NonRetryableEmbeddingError(message) from exc
            if "non-retryable" in message.lower():
                raise NonRetryableEmbeddingError(message) from exc
            raise RetryableEmbeddingError(message) from exc
        self._record_success()
        EMBEDDING_PROVIDER_LATENCY_SECONDS.labels(
            provider=self.settings.embedding_provider,
            model=self.settings.embedding_model,
        ).observe(time.monotonic() - start)
        self._last_run_metadata = EmbeddingRunMetadata(
            provider=self.settings.embedding_provider,
            model=self.settings.embedding_model,
            source="env_fallback",
        )
        return vectors

    @staticmethod
    def _validate_vectors(
        vectors: list[list[float]],
        *,
        dimension: int,
    ) -> list[list[float]]:
        validated: list[list[float]] = []
        for vector in vectors:
            coerced = [float(value) for value in vector]
            if len(coerced) != dimension:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected {dimension}, got {len(coerced)}"
                )
            validated.append(coerced)
        return validated

    def _guard_circuit_state(self) -> None:
        opened_until = self._state.opened_until
        if opened_until is None:
            return
        if datetime.now(tz=UTC) < opened_until:
            raise ApiError(
                code="PROVIDER_CIRCUIT_OPEN",
                message="Embedding provider circuit breaker is open.",
                status_code=503,
            )
        self._state.opened_until = None
        self._state.failures = 0

    def _record_failure(self) -> None:
        self._state.failures += 1
        if self._state.failures >= self.settings.provider_circuit_breaker_threshold:
            self._state.opened_until = datetime.now(tz=UTC) + timedelta(
                seconds=self.settings.provider_circuit_breaker_reset_seconds
            )

    def _record_success(self) -> None:
        self._state.failures = 0
        self._state.opened_until = None

    @staticmethod
    def _redact_failure_reason(reason: str) -> str:
        lowered = reason.lower()
        if "timeout" in lowered:
            return "timeout"
        if "dimension mismatch" in lowered:
            return "dimension_mismatch"
        if "unauthorized" in lowered or "forbidden" in lowered or "auth" in lowered:
            return "authentication_failed"
        if "rate" in lowered and "limit" in lowered:
            return "rate_limited"
        if "connection" in lowered or "dns" in lowered or "refused" in lowered:
            return "connectivity_failure"
        if "non-retryable" in lowered:
            return "invalid_request"
        return "provider_error"

    def _build_failure_context(
        self,
        *,
        provider_type: str,
        model_name: str,
        source: str,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "provider": {
                "type": provider_type,
                "model": model_name,
                "source": source,
            },
            "reason": self._redact_failure_reason(reason),
        }
