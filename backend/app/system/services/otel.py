"""OpenTelemetry setup and redacted spans for the API and background workers.

The runtime deliberately records identities and payloads separately. Trace
attributes contain only low-cardinality operational facts; prompts, tool
arguments, connector tokens, SQL text, and model output never enter a span.
"""

from __future__ import annotations

import functools
import inspect
import logging
from collections.abc import AsyncGenerator, Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, ParamSpec, TypeVar, cast

from opentelemetry import context, propagate, trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from app.core.config import Settings

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")
_configured = False
_instrumented_engine_ids: set[int] = set()


def configure_telemetry(settings: Settings) -> None:
    """Configure one process-wide OTLP provider without changing request flow."""
    global _configured
    if _configured or not settings.otel_enabled:
        return

    resource = Resource.create(
        {
            SERVICE_NAME: settings.otel_service_name,
            "deployment.environment": settings.env,
            "service.version": settings.app_version,
        }
    )
    provider = TracerProvider(resource=resource)
    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=endpoint,
                        insecure=settings.otel_exporter_otlp_insecure,
                    )
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("OpenTelemetry OTLP exporter could not be configured")
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # noqa: BLE001
        # Test runners and reloaders may initialize a provider first. The
        # existing provider remains valid and spans stay non-fatal.
        logger.debug("OpenTelemetry provider was already configured", exc_info=True)
    _configured = True


def _safe_attributes(attributes: Mapping[str, Any] | None) -> dict[str, str | int | float | bool]:
    """Allow only bounded, non-sensitive span values."""
    safe: dict[str, str | int | float | bool] = {}
    for key, value in (attributes or {}).items():
        if value is None or key.lower() in {
            "prompt",
            "content",
            "output",
            "arguments",
            "headers",
            "sql",
        }:
            continue
        if isinstance(value, str | int | float | bool):
            rendered = value if not isinstance(value, str) else value[:256]
            safe[str(key)[:64]] = rendered
    return safe


@contextmanager
def telemetry_span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Span]:
    """Create a current span with redacted operational attributes."""
    tracer = trace.get_tracer("averqel.runtime")
    with tracer.start_as_current_span(name, attributes=_safe_attributes(attributes)) as span:
        yield span


@contextmanager
def extracted_trace_context(headers: Mapping[str, Any] | None) -> Iterator[None]:
    """Continue a W3C trace carried by a Celery task header."""
    carrier = {str(key): str(value) for key, value in (headers or {}).items()}
    token = context.attach(propagate.extract(carrier))
    try:
        yield
    finally:
        context.detach(token)


def inject_trace_context(headers: dict[str, Any]) -> dict[str, Any]:
    """Inject W3C trace context into a Celery-safe JSON header map."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    headers.update(carrier)
    return headers


def trace_async(name: str) -> Callable[[Callable[P, R]], Callable[P, Any]]:
    """Decorate an async model/tool function with a redacted span."""

    def decorator(function: Callable[P, R]) -> Callable[P, Any]:
        @functools.wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> Any:
            attributes: dict[str, Any] = {}
            if args:
                owner = args[0]
                attributes["model.name"] = getattr(owner, "model_name", None)
                if name == "deepspace.tool.execute" and len(args) > 1:
                    attributes["tool.name"] = args[1]
            with telemetry_span(name, attributes):
                return await cast(Any, function)(*args, **kwargs)

        return cast(Callable[P, Any], wrapped)

    return decorator


def trace_async_generator(name: str) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Decorate an async generator so streaming model calls have one span."""

    def decorator(function: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[Any, None]:
            attributes: dict[str, Any] = {}
            if args:
                attributes["model.name"] = getattr(args[0], "model_name", None)
            with telemetry_span(name, attributes):
                async for item in cast(Any, function)(*args, **kwargs):
                    yield item

        return cast(Callable[P, Any], wrapped)

    return decorator


def trace_sync(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate a synchronous worker task with a redacted span."""

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with telemetry_span(name):
                return function(*args, **kwargs)

        return cast(Callable[P, R], wrapped)

    return decorator


def trace_celery_task(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Trace a Celery task and continue its producer trace when present."""

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(function)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            task = args[0] if args else None
            request = getattr(task, "request", None)
            headers = getattr(request, "headers", None)
            with extracted_trace_context(headers), telemetry_span(name):
                return function(*args, **kwargs)

        return cast(Callable[P, R], wrapped)

    return decorator


def instrument_sqlalchemy(engine: Any) -> None:
    """Create redacted PostgreSQL spans around SQLAlchemy cursor activity."""
    engine_id = id(engine)
    if engine_id in _instrumented_engine_ids:
        return
    from sqlalchemy import event

    _instrumented_engine_ids.add(engine_id)

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(connection: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        operation = (statement.strip().split(maxsplit=1)[0] if statement else "unknown").upper()
        connection.info["averqel.db.span"] = trace.get_tracer("averqel.db").start_span(
            "postgresql.query",
            attributes={"db.system": "postgresql", "db.operation": operation},
        )

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(connection: Any, *_args: Any) -> None:
        span = connection.info.pop("averqel.db.span", None)
        if span is not None:
            span.set_status(Status(StatusCode.OK))
            span.end()

    @event.listens_for(engine, "handle_error")
    def handle_error(exception_context: Any) -> None:
        span = exception_context.connection.info.pop("averqel.db.span", None)
        if span is not None:
            span.record_exception(exception_context.original_exception)
            span.set_status(Status(StatusCode.ERROR))
            span.end()


def is_async_callable(value: Any) -> bool:
    """Small public helper for tests validating decorator compatibility."""
    return inspect.iscoroutinefunction(value)
