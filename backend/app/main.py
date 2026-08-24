from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.analytics.api import analytics, dashboard
from app.auth import api as auth
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.deepspace.api import artifacts as deepspace_artifacts
from app.deepspace.api import chats as deepspace_chats
from app.deepspace.api import client_storage
from app.deepspace.api import export as deepspace_export
from app.deepspace.api import library as deepspace_library
from app.documents.api import collections, documents
from app.integrations.api import integrations, mcp
from app.integrations.api import voice as voice_routes
from app.platform.database.session import get_engine
from app.providers.api import providers
from app.query.api import chats, intelligence, queries
from app.system.api import (
    admin,
    app_feedback,
    capabilities,
    feedback,
    health,
    metrics,
    support,
)
from app.system.services.otel import (
    configure_telemetry,
    instrument_sqlalchemy,
    telemetry_span,
)


def _build_cors_kwargs(settings: Settings) -> dict[str, object]:
    origins = list(settings.cors_origins or [])

    # Production-safe behavior:
    # - If explicit origins are configured, use them.
    # - If wildcard is configured, allow all origins explicitly.
    # - Do not silently fall back to a permissive regex.
    if origins == ["*"]:
        return {
            "allow_origins": ["*"],
            "allow_credentials": False,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_telemetry(settings)
    instrument_sqlalchemy(get_engine())

    # Real production version: prefer release_version (git tag), fallback to app_version
    effective_version = settings.release_version or settings.app_version

    app = FastAPI(
        title=settings.app_name,
        version=effective_version,
    )

    app.add_middleware(
        CORSMiddleware,
        **_build_cors_kwargs(settings),
    )

    app.add_middleware(RequestContextMiddleware)

    @app.middleware("http")
    async def opentelemetry_http_middleware(request: Request, call_next):
        """Trace every API request without recording request bodies or secrets."""
        with telemetry_span(
            "http.server",
            {
                "http.request.method": request.method,
                "url.path": request.url.path,
                "server.address": request.url.hostname,
            },
        ) as span:
            try:
                response = await call_next(request)
                span.set_attribute("http.response.status_code", response.status_code)
                return response
            except Exception as exc:  # noqa: BLE001
                span.record_exception(exc)
                raise

    register_exception_handlers(app)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(capabilities.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(documents.router, prefix=settings.api_prefix)
    app.include_router(collections.router, prefix=settings.api_prefix)
    app.include_router(client_storage.router, prefix=settings.api_prefix)
    app.include_router(queries.router, prefix=settings.api_prefix)
    app.include_router(intelligence.router, prefix=settings.api_prefix)
    app.include_router(analytics.router, prefix=settings.api_prefix)
    app.include_router(providers.router, prefix=settings.api_prefix)
    app.include_router(
        feedback.router,
        prefix=settings.api_prefix + "/feedback",
        tags=["feedback"],
    )
    app.include_router(chats.router, prefix=settings.api_prefix)
    app.include_router(deepspace_chats.router, prefix=settings.api_prefix)
    app.include_router(deepspace_export.router, prefix=settings.api_prefix)
    app.include_router(deepspace_library.router, prefix=settings.api_prefix)
    app.include_router(deepspace_artifacts.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    app.include_router(dashboard.router, prefix=settings.api_prefix)
    app.include_router(integrations.router, prefix=settings.api_prefix)
    app.include_router(support.router, prefix=settings.api_prefix)
    app.include_router(app_feedback.router, prefix=settings.api_prefix)
    app.include_router(metrics.router, prefix=settings.api_prefix)
    app.include_router(mcp.router, prefix=settings.api_prefix)
    app.include_router(voice_routes.router, prefix=settings.api_prefix)

    return app


app = create_app()
