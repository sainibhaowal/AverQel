from __future__ import annotations

import asyncio

import pytest

from app.deepspace.integrations.client_proxy import ClientProxyRegistry


class _UnresponsiveWebSocket:
    async def send_json(self, _payload: object) -> None:
        """Accept a packet but deliberately never return an RPC response."""


@pytest.mark.asyncio
async def test_timed_out_client_rpc_unregisters_stale_connection() -> None:
    registry = ClientProxyRegistry()
    websocket = _UnresponsiveWebSocket()
    await registry.register_client("tenant-1", "user-1", websocket)  # type: ignore[arg-type]

    with pytest.raises(asyncio.TimeoutError):
        await registry.db_proxy_call(
            "tenant-1",
            "user-1",
            "db.providers.list_providers",
            {},
            timeout=0.01,
        )

    assert not registry.is_client_connected("tenant-1", "user-1")
