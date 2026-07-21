from __future__ import annotations

from pathlib import Path

_BUILTIN_EMBEDDING_MODELS: dict[str, tuple[str, int]] = {
    "BAAI/bge-small-en-v1.5": ("embeddings/BAAI-bge-small-en-v1.5", 384),
    "intfloat/multilingual-e5-small": (
        "embeddings/intfloat-multilingual-e5-small",
        384,
    ),
}

_BUILTIN_RERANKER_MODELS: dict[str, str] = {
    "BAAI/bge-reranker-v2-m3": "rerankers/BAAI-bge-reranker-v2-m3",
    "cross-encoder/ms-marco-MiniLM-L-12-v2": (
        "rerankers/cross-encoder-ms-marco-MiniLM-L-12-v2"
    ),
}


def get_builtin_embedding_dimension(model_name: str) -> int | None:
    item = _BUILTIN_EMBEDDING_MODELS.get(model_name)
    if item is None:
        return None
    _, dimension = item
    return dimension


def get_builtin_embedding_path(models_root: str, model_name: str) -> Path | None:
    item = _BUILTIN_EMBEDDING_MODELS.get(model_name)
    if item is None:
        return None
    relative_path, _ = item
    return Path(models_root, relative_path)


def get_builtin_reranker_path(models_root: str, model_name: str) -> Path | None:
    relative_path = _BUILTIN_RERANKER_MODELS.get(model_name)
    if relative_path is None:
        return None
    return Path(models_root, relative_path)
