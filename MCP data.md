# AverQel MCP architecture

## Scope

AverQel uses the official Python MCP SDK (`mcp==1.27.1`) as its protocol
client. The SDK handles MCP messages and transports; the AverQel services
around it provide tenancy, OAuth, persistence, policy, lifecycle, and UI.

The marketplace is **official-vendor-only**. AverQel does not display or
install arbitrary community registry packages, Smithery/Pipeboard IDs, or
unknown MCP servers.

## Current official catalog

The catalog currently contains 11 entries:

| Vendor | Server | UI action |
|---|---|---|
| Google | Gmail | Connect |
| Google | Drive | Connect |
| Google | Calendar | Connect |
| Google | Chat | Connect |
| Google | People | Connect |
| Notion | Notion | Connect |
| GitHub | GitHub | Connect |
| Slack | Slack | Setup required |
| Figma | Figma | Setup required |
| Microsoft | Microsoft Learn | Connect |
| SeedLegals | SeedLegals | Connect |

This is a curated directory, not a claim that every public MCP server is
official or safe. Slack and Figma require vendor-specific client registration
and therefore cannot be presented as universal one-click OAuth connections.

## Request lifecycle

```text
User opens /dashboard/mcp
        |
        v
GET /api/v1/mcp/catalog       official entries only
        |
        v
User clicks Connect
        |
        v
POST /api/v1/mcp/servers      create tenant/user-owned server row
        |
        +--> oauth/start       MCP metadata discovery + PKCE
        |          |
        |          v
        |      vendor consent
        |          |
        |          v
        +--> oauth/callback    signed state and ownership validation
                   |
                   v
             encrypted token storage
                   |
                   v
             MCP initialize and catalog loading
                   |
                   v
             tools/prompts/resources/templates
                   |
                   v
             DeepSpace namespaced tool registry
                   |
                   v
             permission/approval checks -> tool call -> durable events
```

## Backend components

- `backend/app/services/integrations/mcp_registry.py` is the allowlisted
  official catalog. Unknown `vendor_slug` values are rejected.
- `backend/app/services/integrations/mcp_runtime.py` is the native SDK adapter.
  It supports Streamable HTTP, SSE fallback during initialization, and stdio;
  paginates and normalizes tools, prompts, resources, and templates; and
  handles list-change notifications.
- `backend/app/services/integrations/mcp_oauth_service.py` performs MCP
  authorization-server/resource metadata discovery, PKCE, optional dynamic
  client registration, signed expiring state, callback validation, token
  exchange, and refresh persistence.
- `backend/app/models/integrations/mcp_server.py` defines durable server,
  event, and encrypted OAuth-token records.
- `backend/app/repositories/mcp_events.py` appends and reads ordered events.
- `backend/app/api/v1/mcp.py` exposes server, OAuth, catalog, refresh,
  disconnect, and inspector endpoints.
- `backend/app/worker/tasks_mcp.py` runs catalog refresh, refresh-token work,
  notification processing, reconnect backoff, and lifecycle monitoring.
- `backend/alembic/versions/20260716_0001_mcp_runtime_tables.py` through
  `20260716_0004_seed_connector_oauth_metadata.py` are the database migrations.

## DeepSpace integration

DeepSpace receives MCP tools only from tenant/user-owned `MCPServer` rows.
Tools are namespaced by server, checked by the normal permission and approval
policy, and executed through the MCP runtime. Tool requests, results, failures,
catalog changes, OAuth events, and lifecycle changes are persisted with
redacted payloads.

Legacy connector records remain isolated for backward-compatible connector
sync APIs. They are not used as the DeepSpace MCP tool source and do not feed
the official MCP marketplace.

## Frontend

- `/dashboard/mcp` shows installed server status and the official catalog.
- `Connect` starts the vendor OAuth flow when the vendor supports it.
- `Setup required` opens the vendor documentation for fixed-client setup.
- `Refresh catalog` reloads live MCP capabilities.
- `Inspect` shows diagnostics and persisted events.
- `Disconnect` deletes the tenant/user-owned server and encrypted token.

## Verification state

The current environment has:

- PostgreSQL migration head `20260716_0004`;
- API, worker, scheduler, frontend, PostgreSQL, and Redis containers running;
- readiness endpoint returning HTTP 200;
- focused MCP/OAuth/registry/runtime tests passing;
- a live anonymous Microsoft Learn MCP handshake discovering three tools.

Production completion still requires real OAuth registrations and accounts for
the vendors that require consent (for example Google, GitHub, Notion, and
Slack), plus provider-backed end-to-end tests. The architecture cannot create
or bypass those vendor credentials.
