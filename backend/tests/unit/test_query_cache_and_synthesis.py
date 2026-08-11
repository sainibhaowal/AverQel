from uuid import uuid4

import pytest

from app.query.services.chunk_cache import ChunkMetadataCache
from app.query.services.retrieval_service import RetrievedChunk
from app.query.services.synthesis_service import (
    MatrixCell,
    _score_overlap,
    _status_from_score,
    _tokenize,
    build_synthesis_matrix,
)


def test_synthesis_helpers_and_matrix_statuses() -> None:
    assert _tokenize("The quick fox and a dog") == {"quick", "fox", "dog"}
    assert _score_overlap(set(), {"x"}) == 0
    assert _score_overlap({"a", "b"}, {"a"}) == 0.5
    assert _status_from_score(0.8) == "supported"
    assert _status_from_score(0.2) == "partial"
    assert _status_from_score(0.01) == "not_found"
    assert build_synthesis_matrix([], ["finding"]).cells == []
    assert build_synthesis_matrix([], []).findings == []

    document_id, chunk_id = uuid4(), uuid4()
    chunks = [
        RetrievedChunk(document_id, chunk_id, "b.md", "Alpha beta evidence", 0.9, page_number=2),
        RetrievedChunk(document_id, uuid4(), "a.md", "Unrelated text", 0.5),
    ]
    result = build_synthesis_matrix(chunks, ["Alpha beta", "  "])
    assert result.documents == ["a.md", "b.md"]
    assert len(result.cells) == 2
    assert all(isinstance(cell, MatrixCell) for cell in result.cells)
    assert next(cell for cell in result.cells if cell.document == "b.md").status == "supported"


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        del ttl
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    def pipeline(self) -> "_FakeRedis":
        return self

    def __enter__(self) -> "_FakeRedis":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self) -> None:
        return None


def test_chunk_metadata_cache_round_trip_and_failures() -> None:
    cache = ChunkMetadataCache(ttl=10)
    redis = _FakeRedis()
    cache._redis = redis
    chunk_id = uuid4()
    assert cache.get(chunk_id) is None
    cache.set(chunk_id, {"created": object(), "value": 2})
    assert cache.get(chunk_id)["value"] == 2  # type: ignore[index]
    assert cache.get_many([chunk_id, uuid4()])[chunk_id]["value"] == 2
    cache.set_many({chunk_id: {"batch": True}})
    assert cache.get(chunk_id)["batch"] is True  # type: ignore[index]
    cache.delete(chunk_id)
    assert cache.get(chunk_id) is None
    assert cache.get_many([]) == {}

    class _Broken:
        def get(self, _key: str) -> str:
            raise RuntimeError("down")

        def setex(self, *_args: object) -> None:
            raise RuntimeError("down")

        def delete(self, _key: str) -> None:
            raise RuntimeError("down")

    cache._redis = _Broken()
    assert cache.get(chunk_id) is None
    cache.set(chunk_id, {"x": 1})
    cache.delete(chunk_id)
    with pytest.raises(ValueError):
        ChunkMetadataCache(ttl=0)
