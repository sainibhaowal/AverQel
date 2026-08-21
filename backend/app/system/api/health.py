from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.ingestion.services.security.malware_scan_service import MalwareScanService
from app.platform.database.session import get_engine
from app.system.schemas.common import HealthResponse
from app.system.services.cache_service import get_redis_client

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.release_version or settings.app_version,
        git_sha=settings.git_sha,
        build_timestamp_utc=settings.build_timestamp_utc,
    )


@router.get("/ready", response_model=HealthResponse)
def ready(settings: Settings = Depends(get_settings)) -> HealthResponse:
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

    if settings.malware_scan_enabled and settings.malware_scan_required:
        if not MalwareScanService(settings).check_available():
            raise ApiError(
                code="MALWARE_SCANNER_NOT_READY",
                message="Malware scanner dependency is not ready.",
                status_code=503,
            )

    return HealthResponse(
        status="ok",
        version=settings.release_version or settings.app_version,
        git_sha=settings.git_sha,
        build_timestamp_utc=settings.build_timestamp_utc,
    )
