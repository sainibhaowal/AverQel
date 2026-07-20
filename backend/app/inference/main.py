from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.core.config import get_settings
from app.inference.runtime import LocalInferenceRuntime
from app.schemas.inference import (
    EmbedRequest,
    EmbedResponse,
    RerankItem,
    RerankRequestPayload,
    RerankResponsePayload,
)


settings = get_settings()
runtime = LocalInferenceRuntime(settings)
embedding_semaphore = asyncio.Semaphore(settings.local_inference_embedding_concurrency)
rerank_semaphore = asyncio.Semaphore(settings.local_inference_rerank_concurrency)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ = app
    if settings.local_model_warmup_enabled:
        await asyncio.to_thread(runtime.warmup)
    yield


app = FastAPI(title="AverQel Local Inference", version="0.1.0", lifespan=lifespan)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/embed", response_model=EmbedResponse)
async def embed(payload: EmbedRequest) -> EmbedResponse:
    async with embedding_semaphore:
        vectors = await asyncio.to_thread(
            runtime.embed_many,
            model_name=payload.model,
            texts=payload.texts,
            batch_size=payload.batch_size,
            normalize=payload.normalize,
        )
    return EmbedResponse(vectors=vectors)


@app.post("/rerank", response_model=RerankResponsePayload)
async def rerank(payload: RerankRequestPayload) -> RerankResponsePayload:
    async with rerank_semaphore:
        scored = await asyncio.to_thread(
            runtime.rerank,
            model_name=payload.model,
            query=payload.query,
            documents=payload.documents,
        )
    return RerankResponsePayload(
        results=[
            RerankItem(index=index, score=score)
            for index, score in scored[: payload.top_n]
        ]
    )
