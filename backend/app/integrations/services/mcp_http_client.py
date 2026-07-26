"""SSRF-safe HTTP clients used by native MCP and MCP OAuth flows."""

from __future__ import annotations

import httpcore
import httpx

from app.integrations.services.mcp_endpoint_security import (
    resolve_public_addresses,
    validate_remote_endpoint,
)


class MCPRedirectRejectedError(ValueError):
    """Raised when an MCP endpoint attempts an unvalidated redirect."""


class _PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connect to the exact public address resolved immediately before connect."""

    def __init__(self) -> None:
        self._backend = (
            httpcore.AsyncNetworkBackend()
            if hasattr(httpcore, "AsyncNetworkBackend")
            else getattr(httpcore, "AutoBackend", httpcore.AnyIOBackend)()
        )

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        errors: list[Exception] = []
        for address in resolve_public_addresses(host, port):
            try:
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        raise MCPRedirectRejectedError("MCP endpoint could not establish a safe connection") from (errors[-1] if errors else None)


class _PinnedSyncNetworkBackend(httpcore.NetworkBackend):
    """Synchronous equivalent of the pinned MCP network backend."""

    def __init__(self) -> None:
        self._backend = (
            httpcore.SyncBackend()
            if hasattr(httpcore, "SyncBackend")
            else getattr(httpcore, "AutoBackend", httpcore.SyncBackend)()
        )

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        errors: list[Exception] = []
        for address in resolve_public_addresses(host, port):
            try:
                return self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        raise MCPRedirectRejectedError("MCP endpoint could not establish a safe connection") from (errors[-1] if errors else None)


class SafeMCPClient(httpx.Client):
    """Synchronous client that validates every destination and never follows redirects."""

    def __init__(self, *args, **kwargs):
        kwargs["follow_redirects"] = False
        super().__init__(*args, **kwargs)
        if hasattr(self, "_transport") and hasattr(self._transport, "_pool"):
            self._transport._pool._network_backend = _PinnedSyncNetworkBackend()

    def send(self, request, *, stream=False, auth=httpx.USE_CLIENT_DEFAULT, follow_redirects=httpx.USE_CLIENT_DEFAULT):
        validate_remote_endpoint(str(request.url))
        response = super().send(
            request,
            stream=stream,
            auth=auth,
            follow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            response.close()
            raise MCPRedirectRejectedError("MCP endpoint redirects are not permitted")
        return response


class SafeMCPAsyncClient(httpx.AsyncClient):
    """Asynchronous client that validates every destination and never follows redirects."""

    def __init__(self, *args, **kwargs):
        kwargs["follow_redirects"] = False
        super().__init__(*args, **kwargs)
        if hasattr(self, "_transport") and hasattr(self._transport, "_pool"):
            self._transport._pool._network_backend = _PinnedAsyncNetworkBackend()

    async def send(self, request, *, stream=False, auth=httpx.USE_CLIENT_DEFAULT, follow_redirects=httpx.USE_CLIENT_DEFAULT):
        validate_remote_endpoint(str(request.url))
        response = await super().send(
            request,
            stream=stream,
            auth=auth,
            follow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise MCPRedirectRejectedError("MCP endpoint redirects are not permitted")
        return response


def build_safe_sync_client(*, timeout: float = 30.0, headers: dict[str, str] | None = None) -> SafeMCPClient:
    return SafeMCPClient(timeout=timeout, headers=headers, trust_env=False)


def build_safe_async_client(
    *,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | float | None = None,
    auth: httpx.Auth | None = None,
) -> SafeMCPAsyncClient:
    return SafeMCPAsyncClient(headers=headers, timeout=timeout, auth=auth, trust_env=False)
