from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApiError
from app.platform.database.session import get_engine
from app.system.schemas.common import HealthResponse
from app.system.services.cache_service import get_redis_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise ApiError(
            code="DATABASE_NOT_READY",
            message="Database dependency is not ready.",
            status_code=503,
        ) from exc

    try:
        redis_client = get_redis_client()
        redis_client.ping()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            code="REDIS_NOT_READY",
            message="Redis dependency is not ready.",
            status_code=503,
        ) from exc

    return HealthResponse(status="ok")
