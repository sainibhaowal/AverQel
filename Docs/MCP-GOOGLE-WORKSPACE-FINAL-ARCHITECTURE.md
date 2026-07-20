# AverQel Google Workspace MCP Architecture

**Status:** Plan authority for the first MCP product scope
**Scope:** Official remote Google Workspace MCP services only
**Products:** Gmail, Drive, Calendar, Docs, and Sheets
**Excluded:** Public registry browsing for users, community servers, local
stdio, arbitrary endpoints, arbitrary headers, and hardcoded vendor adapters

## Product Goal

AverQel provides one trusted marketplace card per approved Google Workspace
MCP service. Users see official metadata, open details, click one Connect
button, complete the required Google authentication, and use the real
authorized tools through DeepSpace.

```text
Official Google source or manifest
              |
              v
     Internal catalog intake
              |
              v
 Endpoint, ownership, auth, and policy review
              |
              v
       Approved catalog record
              |
              v
       Google Workspace card
              |
              v
        User clicks Connect
              |
              v
      Generic/dynamic Google OAuth
              |
              v
      Encrypted per-user token
              |
              v
         Real MCP handshake
              |
              v
     tools/list and authorized tools
              |
              v
       Permissioned DeepSpace call
```

## No Hardcoded Vendor Design

Frontend and backend contain generic MCP behavior only. Google facts are
reviewed catalog data and secret references:

| Data | Storage |
|---|---|
| Product name, logo, publisher, description | `mcp_registry_entries` |
| MCP endpoint and transport | `mcp_registry_entries` |
| Auth declaration and scopes | catalog metadata |
| Documentation and privacy links | raw/normalized catalog metadata |
| Categories and trust state | `mcp_registry_entries` |
| Tool preview and count | catalog metadata and tenant cache |
| OAuth client reference | deployment secret manager reference |
| User access/refresh token | encrypted `mcp_oauth_tokens` payload |

No Google product name, logo, URL, tool name, OAuth secret, or scope is
compiled into a React component or MCP runtime branch.

## Trust Boundary

The public MCP Registry is internal intake only. It is not a user-facing
marketplace.

```text
discovered -> source validated -> ownership verified -> endpoint verified
           -> auth tested -> catalog tested -> policy reviewed -> approved
```

Only `trust_status=approved` records are returned by user marketplace,
catalog, and facet APIs. `discovered`, `rejected`, and `blocked` records are
admin/internal data only.

## Card Contract

Each approved card renders API data for:

- Logo and canonical product name.
- Publisher and official/AverQel verification badge.
- Official description and category.
- Remote transport and authentication requirement.
- Tool count or `Connect to reveal tools`.
- Last catalog update.
- `View details` and generated `Connect <name>` actions.

The Connect button is disabled unless the catalog record is approved. The
label is generated from the stored catalog name, never from a vendor branch.

## Details Contract

The details view shows logo, name, publisher, source, description, MCP URL,
transport, authentication method, scopes, categories, tool count, tool names,
tool descriptions, documentation, privacy/support links, verification time,
catalog time, and one Connect action.

It never shows client secrets, access tokens, refresh tokens, or arbitrary
headers. Private tools show `Connect to reveal tools` until authorization.

## Authentication Contract

| Catalog auth | User experience | Server requirement |
|---|---|---|
| `anonymous` | Connect immediately | Public remote MCP endpoint |
| `oauth_dynamic` | Click Connect and complete consent | Metadata, PKCE, state, redirect validation |
| `oauth_vendor` | Click Connect and complete consent | Client ID/secret in secret manager |
| `setup_required` | Show official setup requirement | Do not connect until supported |

Google client credentials, when required, are deployment secrets. The catalog
stores only a secret reference. Each user receives an independent token:

```text
tenant_id + user_id + server_id -> encrypted access/refresh token
```

## End-to-End Runtime

```text
Connect
 -> verify approved catalog entry
 -> create tenant-owned MCPServer
 -> start generic OAuth if needed
 -> validate callback state and code
 -> encrypt user token
 -> queue catalog refresh
 -> initialize Streamable HTTP/SSE session
 -> list tools/prompts/resources with pagination
 -> normalize schemas and persist bounded catalog
 -> expose namespaced tools to DeepSpace
 -> enforce permission and approval policy
 -> execute with the user's token
 -> persist redacted audit event
```

Read, write, send, delete, and administrative tools must have different risk
and approval policies.

## API Surface

All routes use `/api/v1`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/mcp/marketplace` | Search, paginate, filter, and sort approved Google records |
| GET | `/mcp/marketplace/facets` | Return filter values from approved catalog data |
| GET | `/mcp/catalog` | Return approved Google catalog records |
| POST | `/mcp/marketplace/{entry_id}/connect` | Start an approved connection |
| GET | `/mcp/servers` | List the current user's connections |
| POST | `/mcp/servers/{id}/oauth/start` | Start/restart OAuth |
| GET | `/mcp/servers/{id}/oauth/callback` | Complete OAuth |
| POST | `/mcp/servers/{id}/refresh` | Refresh live catalog |
| GET | `/mcp/servers/{id}/inspector` | Show owned-server diagnostics |
| DELETE | `/mcp/servers/{id}` | Disconnect an owned server |
| POST | `/mcp/catalog/{entry_id}/review` | Admin approve/reject an intake record |

There is no public registry synchronization route, raw manifest import route,
raw manifest submission route, API-key entry route, or arbitrary endpoint/header
route. Google catalog records are introduced only through the controlled
official-source curation process.

Admin catalog routes require `mcp:catalog:manage`. Normal users cannot submit
URLs, commands, headers, or arbitrary MCP servers.

Query parameters are `q`, `category`, `transport`, `auth_type`, `sort`, `page`,
and `page_size`. Sort values are `default`, `popular`, `trending`, `new`, and
`alphabetical`. Every query is constrained to approved Google records.

## Exact Code Areas

### Backend

- `backend/app/api/v1/mcp.py`: API contracts and approval boundary.
- `backend/app/models/integrations/mcp_server.py`: catalog, connection, event,
  and encrypted token models.
- `backend/app/services/integrations/mcp_registry_sync.py`: intake and
  normalization.
- `backend/app/services/integrations/mcp_endpoint_security.py`: HTTPS/SSRF.
- `backend/app/services/integrations/mcp_oauth_service.py`: generic OAuth.
- `backend/app/services/integrations/connector_oauth_service.py`: OAuth helpers.
- `backend/app/services/integrations/mcp_runtime.py`: remote MCP sessions and
  tool/resource/prompt operations.
- `backend/app/services/security/connector_secret_crypto.py`: encryption.
- `backend/app/worker/tasks_mcp.py`: enrichment, refresh, retry, lifecycle.
- `backend/app/worker/celery_app.py`: scheduled jobs.
- `backend/alembic/versions/`: schema and trust migrations.

### Frontend

- `frontend/app/dashboard/mcp/page.tsx`: marketplace, search, filters, sort,
  cards, details, connect, installed view, and statuses.
- `frontend/app/dashboard/mcp/inspector/[id]/page.tsx`: diagnostics.
- `frontend/lib/api.ts`: authenticated tenant-aware requests.
- `frontend/tests/mcp-page.test.ts`: query/filter/sort tests.
- `frontend/tests/mcp-page.render.test.tsx`: UI and modal tests.

## Security Invariants

- Catalog metadata is shared; tenant connections are isolated.
- Runtime/token/event tables retain tenant/user RLS boundaries.
- Intake records cannot create user connections until approved.
- OAuth state is signed, short-lived, single-use, and redirect-bound.
- OAuth tokens are encrypted with tenant-bound associated data.
- Endpoint validation runs before import and connection; runtime egress is
  revalidated after redirects/DNS changes.
- Tool arguments and event payloads are redacted before persistence/logging.
- No private Google content is background-crawled before explicit user action.
- Existing connector integrations, DeepSpace approvals, queues, and events
  must not regress.

## Completion Gate

Google Workspace is complete only when official source evidence, endpoint,
transport, OAuth scopes, real tool discovery, token isolation, permissioned
read/write/send/delete tests, disconnect behavior, local smoke tests, and VPS
smoke tests all pass. Until then, the UI must show no Google card rather than
inventing metadata.
