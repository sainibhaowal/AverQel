from __future__ import annotations

import importlib
from threading import Lock
from typing import Any

from app.core.config import Settings
from app.services.providers.builtin_local_models import (
    get_builtin_embedding_path,
    get_builtin_reranker_path,
)


class LocalInferenceRuntime:
    _embedding_models: dict[str, Any] = {}
    _reranker_models: dict[str, Any] = {}
    _lock = Lock()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _sentence_transformers_module() -> Any:
        return importlib.import_module("sentence_transformers")

    def _resolve_embedding_model_path(self, model_name: str) -> str:
        path = get_builtin_embedding_path(self.settings.local_models_root, model_name)
        if path is None or not path.exists():
            raise RuntimeError(f"Local embedding model is missing: {model_name}")
        return str(path)

    def _resolve_reranker_model_path(self, model_name: str) -> str:
        path = get_builtin_reranker_path(self.settings.local_models_root, model_name)
        if path is None or not path.exists():
            raise RuntimeError(f"Local reranker model is missing: {model_name}")
        return str(path)

    def load_embedding_model(self, model_name: str) -> Any:
        existing = self._embedding_models.get(model_name)
        if existing is not None:
            return existing
        with self._lock:
            existing = self._embedding_models.get(model_name)
            if existing is not None:
                return existing
            module = self._sentence_transformers_module()
            sentence_transformer = module.SentenceTransformer
            loaded = sentence_transformer(
                self._resolve_embedding_model_path(model_name),
                local_files_only=True,
            )
            self._embedding_models[model_name] = loaded
            return loaded

    def load_reranker_model(self, model_name: str) -> Any:
        existing = self._reranker_models.get(model_name)
        if existing is not None:
            return existing
        with self._lock:
            existing = self._reranker_models.get(model_name)
            if existing is not None:
                return existing
            module = self._sentence_transformers_module()
            cross_encoder = module.CrossEncoder
            loaded = cross_encoder(
                self._resolve_reranker_model_path(model_name),
                local_files_only=True,
            )
            self._reranker_models[model_name] = loaded
            return loaded

    def embed_many(
        self,
        *,
        model_name: str,
        texts: list[str],
        batch_size: int,
        normalize: bool,
    ) -> list[list[float]]:
        model = self.load_embedding_model(model_name)
        encoded = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return [[float(value) for value in raw.tolist()] for raw in encoded]

    def rerank(
        self,
        *,
        model_name: str,
        query: str,
        documents: list[str],
    ) -> list[tuple[int, float]]:
        model = self.load_reranker_model(model_name)
        pairs = [(query, document) for document in documents]
        raw_scores = model.predict(pairs, show_progress_bar=False)
        scored = [(index, float(score)) for index, score in enumerate(raw_scores)]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    def warmup(self) -> None:
        if self.settings.embedding_provider == "sentence-transformers":
            self.load_embedding_model(self.settings.embedding_model)
        if (
            self.settings.reranking_enabled
            and self.settings.reranking_provider == "sentence-transformers"
        ):
            self.load_reranker_model(self.settings.reranking_model)
