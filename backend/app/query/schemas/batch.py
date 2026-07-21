"""Schemas for batched query execution."""

from pydantic import BaseModel

from app.query.schemas.queries import QueryRequest, QueryResponse


class BatchQueryRequest(BaseModel):
    queries: list[QueryRequest]


class BatchQueryResponse(BaseModel):
    results: list[QueryResponse]
