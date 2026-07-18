from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

_trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
_tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


@dataclass(slots=True, frozen=True)
class RequestContextTokens:
    """Reset tokens for request-scoped context variables."""

    trace_token: Token[str | None]
    tenant_token: Token[str | None]
    user_token: Token[str | None]


@dataclass(slots=True, frozen=True)
class RequestContextSnapshot:
    """Current request-scoped identity snapshot."""

    trace_id: str | None
    tenant_id: str | None
    user_id: str | None


def bind_request_context(
    trace_id: str,
    tenant_id: str | None,
    user_id: str | None,
) -> RequestContextTokens:
    """Bind request-scoped identifiers into ContextVars and return reset tokens."""
    return RequestContextTokens(
        trace_token=_trace_id_ctx.set(trace_id),
        tenant_token=_tenant_id_ctx.set(tenant_id),
        user_token=_user_id_ctx.set(user_id),
    )


def clear_request_context(tokens: RequestContextTokens) -> None:
    """Restore previous ContextVar values using the provided reset tokens."""
    _trace_id_ctx.reset(tokens.trace_token)
    _tenant_id_ctx.reset(tokens.tenant_token)
    _user_id_ctx.reset(tokens.user_token)


def get_trace_id() -> str | None:
    """Return the current request trace id."""
    return _trace_id_ctx.get()


def get_tenant_id() -> str | None:
    """Return the current request tenant id."""
    return _tenant_id_ctx.get()


def get_user_id() -> str | None:
    """Return the current request user id."""
    return _user_id_ctx.get()


def get_request_context_snapshot() -> RequestContextSnapshot:
    """Return the current request context as an immutable snapshot."""
    return RequestContextSnapshot(
        trace_id=_trace_id_ctx.get(),
        tenant_id=_tenant_id_ctx.get(),
        user_id=_user_id_ctx.get(),
    )


def set_trace_id(trace_id: str | None) -> None:
    """Update the current request trace id."""
    _trace_id_ctx.set(trace_id)


def set_tenant_id(tenant_id: str | None) -> None:
    """Update the current request tenant id."""
    _tenant_id_ctx.set(tenant_id)


def set_user_id(user_id: str | None) -> None:
    """Update the current request user id."""
    _user_id_ctx.set(user_id)


def clear_trace_id() -> None:
    """Clear the current request trace id."""
    _trace_id_ctx.set(None)


def clear_tenant_id() -> None:
    """Clear the current request tenant id."""
    _tenant_id_ctx.set(None)


def clear_user_id() -> None:
    """Clear the current request user id."""
    _user_id_ctx.set(None)
