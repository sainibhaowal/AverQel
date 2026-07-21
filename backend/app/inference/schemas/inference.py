"""Request and response schemas for the local inference service."""

from pydantic import BaseModel


class EmbedRequest(BaseModel):
    model: str
    texts: list[str]
    batch_size: int = 32
    normalize: bool = True


class EmbedResponse(BaseModel):
    vectors: list[list[float]]


class RerankRequestPayload(BaseModel):
    model: str
    query: str
    documents: list[str]
    top_n: int = 5


class RerankItem(BaseModel):
    index: int
    score: float


class RerankResponsePayload(BaseModel):
    results: list[RerankItem]
