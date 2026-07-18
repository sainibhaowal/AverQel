from __future__ import annotations

import hashlib
import struct
from collections.abc import Sequence

from app.services.providers.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResult,
    ProviderModelInfo,
)


class LocalDeterministicEmbeddingProvider:
    provider_name = "local-deterministic"

    @staticmethod
    def _deterministic_vector(text: str, dimension: int) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        for idx in range(dimension):
            start = (idx * 4) % len(digest)
            chunk = digest[start : start + 4]
            integer_value = struct.unpack("!I", chunk)[0]
            normalized = (integer_value / 2**32) * 2 - 1
            values.append(round(normalized, 7))
        return values

    def embed_many(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[
                self._deterministic_vector(text, request.dimension)
                for text in request.texts
            ]
        )

    def list_embedding_models(self) -> Sequence[ProviderModelInfo]:
        return [
            ProviderModelInfo(
                name="hash-fallback", kind="embedding", capabilities={"local": True}
            )
        ]

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(status="healthy", latency_ms=0)
