# Google Workspace MCP Implementation Plan

**Plan status:** Awaiting approval before implementation
**Product scope:** Google Workspace only: Gmail, Drive, Calendar, Docs, and
Sheets
**Connection scope:** Official remote MCP endpoints using anonymous access,
dynamic OAuth, or vendor-configured OAuth
**Explicitly excluded:** local stdio, community servers, arbitrary remote
URLs, arbitrary headers, and vendor-specific code branches

This plan turns
[`MCP-GOOGLE-WORKSPACE-FINAL-ARCHITECTURE.md`](MCP-GOOGLE-WORKSPACE-FINAL-ARCHITECTURE.md)
into production work. No phase should be marked complete from a database row
alone: the source, endpoint, authentication, catalog, tenant isolation, and
user experience must all be verified.

## Current Baseline

The existing system already has a generic remote MCP client, registry intake,
catalog APIs, OAuth/token services, tenant-owned server records, catalog
refresh workers, a marketplace page, installed-server status, and DeepSpace
tool exposure. Public registry rows are internal intake data. The marketplace
must remain approved-only.

Legacy discovered registry rows are removed by the cleanup migration. They are
not Google Workspace cards and must not return through a background sync. No
Google product endpoint, logo, tool list, OAuth secret, or scope will be
invented to make the UI look populated.

## Phase 0: Safety Lock and Baseline

**Why:** Prevent unverified registry records or legacy connection paths from
leaking into the trusted Google marketplace while implementation is underway.

**Files and areas:**

- `backend/app/api/v1/mcp.py`
- `backend/app/models/integrations/mcp_server.py`
- `backend/app/services/integrations/mcp_endpoint_security.py`
- `frontend/app/dashboard/mcp/page.tsx`
- `backend/tests/integration/test_mcp_api.py`
- `frontend/tests/mcp-page.test.ts`
- `frontend/tests/mcp-page.render.test.tsx`

**Work:**

1. Confirm every user-facing catalog, marketplace, facet, and connect query
   requires `trust_status=approved` and the remote transport policy.
2. Keep discovered, rejected, blocked, and pending records out of the user
   marketplace.
3. Keep local stdio and arbitrary endpoint/header controls unavailable in the
   normal user flow without deleting shared runtime code prematurely.
4. Keep the public registry sync, raw manifest import/submission, and API-key
   UI removed.
5. Capture current API, TypeScript, and container smoke-test baselines.

**Acceptance:** A normal user sees zero Google cards until an approved,
verified record exists. Existing tenants and non-MCP integrations continue to
load.

## Phase 1: Official Google Source Intake

**Why:** Real names, logos, descriptions, endpoints, and auth requirements
must come from official evidence, not frontend constants or guessed URLs.

**Files and areas:**

- `backend/app/services/integrations/mcp_registry_sync.py`
- `backend/app/api/v1/mcp.py`
- `backend/app/models/integrations/mcp_server.py`
- `backend/alembic/versions/` for any schema change
- `backend/tests/unit/test_mcp_marketplace_metadata.py`
- `backend/tests/integration/test_mcp_api.py`
- `Docs/MCP-GOOGLE-WORKSPACE-FINAL-ARCHITECTURE.md`

**Work:**

1. Define a source record for each Google Workspace MCP service with source
   URL, publisher evidence, endpoint evidence, transport, auth declaration,
   documentation, privacy/support links, and retrieval timestamp.
2. Import only official Google or officially operated MCP sources. A public
   registry row is evidence to review, not proof of ownership.
3. Normalize a stable `provider_id` and `product_id`; deduplicate by canonical
   endpoint and publisher identity, not display name.
4. Reject records with missing ownership, non-HTTPS endpoints, unsupported
   transport, ambiguous publisher, or unverifiable metadata.

**Acceptance:** Each approved candidate has traceable official source evidence
and a real endpoint. Failed candidates remain pending/rejected and are not
shown to users.

## Phase 2: Catalog Schema and Review Workflow

**Why:** The marketplace needs durable, reviewable metadata without hardcoded
vendor branches, and catalog metadata must remain separate from tenant data.

**Files and areas:**

- `backend/app/models/integrations/mcp_server.py`
- `backend/alembic/versions/`
- `backend/app/api/v1/mcp.py`
- `backend/app/services/integrations/mcp_registry_sync.py`
- `backend/tests/integration/test_mcp_api.py`

**Required catalog fields:**

| Field | Purpose |
|---|---|
| `provider_id` | Stable publisher identity |
| `product_id` | Stable Google product identity |
| `name` | User-facing canonical name |
| `logo_url` | Official or approved brand asset |
| `description` | Official product description |
| `remote_url` | Canonical MCP endpoint |
| `transport` | Streamable HTTP or SSE |
| `auth_type` | Anonymous, dynamic OAuth, or vendor OAuth |
| `oauth_metadata_url` | Optional discovered OAuth metadata source |
| `oauth_secret_ref` | Secret-manager reference only |
| `scopes` | Approved OAuth scope set |
| `documentation_url` | Official documentation |
| `privacy_url` | Official privacy policy |
| `categories` | Search/filter taxonomy |
| `trust_status` | Review state |
| `source` | Official source reference |
| `mcp_catalog_tool_count` | Last real catalog count |
| `mcp_catalog_last_sync_at` | Last successful catalog time |

**Acceptance:** Schema validation prevents incomplete or untrusted records from
being approved. A migration is reversible and does not rewrite tenant tokens
or existing server credentials.

## Phase 3: Google OAuth and Credential Safety

**Why:** Users need a normal Connect flow while AverQel keeps credentials out
of source code, logs, browser storage, and shared catalog rows.

**Files and areas:**

- `backend/app/services/integrations/mcp_oauth_service.py`
- `backend/app/services/integrations/connector_oauth_service.py`
- `backend/app/services/security/connector_secret_crypto.py`
- `backend/app/api/v1/mcp.py`
- `backend/app/models/integrations/mcp_server.py`
- `frontend/app/dashboard/mcp/page.tsx`
- `frontend/lib/api.ts`
- `backend/tests/unit/`
- `backend/tests/integration/test_mcp_api.py`

**Work:**

1. Prefer MCP-discovered OAuth metadata when the official endpoint supports
   it; otherwise use a reviewed Google OAuth profile.
2. Store Google client ID/secret only in the deployment secret manager. Store
   only a reference in catalog metadata.
3. Use authorization-code flow with PKCE, signed short-lived state, exact
   redirect validation, single-use state, and tenant/user binding.
4. Encrypt each user's access and refresh token with tenant/user associated
   data. Never return token material to the frontend.
5. Request only approved scopes and handle denied, expired, revoked, and
   re-consent states explicitly.

**Acceptance:** Two users in different tenants cannot read or use each other's
tokens. OAuth callback replay fails. A revoked Google grant produces a clear
reauthentication status without exposing secrets.

## Phase 4: Real MCP Catalog Enrichment

**Why:** Cards and details must show real tools and descriptions when the
endpoint permits them, while protected tools must not be fabricated or
background-crawled with a user's private data.

**Files and areas:**

- `backend/app/services/integrations/mcp_runtime.py`
- `backend/app/worker/tasks_mcp.py`
- `backend/app/services/integrations/mcp_endpoint_security.py`
- `backend/app/api/v1/mcp.py`
- `backend/tests/integration/`
- `backend/tests/live/` or the repository's live-test location

**Work:**

1. Validate the endpoint before every session and after redirects.
2. Initialize the remote MCP session using the stored auth mechanism.
3. Call `tools/list` with protocol pagination and persist bounded names,
   descriptions, input schemas, and revision metadata.
4. Refresh prompts, resources, and resource templates only when supported by
   the server and policy.
5. Mark catalog state as pending, ready, stale, failed, or authentication
   required. Never treat a missing catalog as an empty tool list.
6. After a user's successful connection, refresh the tenant catalog and
   replace any public preview with the authorized catalog.

**Acceptance:** A public catalog is clearly labeled as public preview. A
protected Google service shows authentication required until Connect succeeds.
After connection, the installed view shows the real tool count and names from
that tenant's live MCP session.

## Phase 5: Claude-Style Marketplace UI

**Why:** Users should discover trusted Google products by card, understand the
connection requirement, and connect without seeing implementation controls.

**Files and areas:**

- `frontend/app/dashboard/mcp/page.tsx`
- `frontend/lib/api.ts`
- `frontend/tests/mcp-page.test.ts`
- `frontend/tests/mcp-page.render.test.tsx`

**UI contract:**

- Search by product, publisher, description, category, and tool metadata.
- `Filter by` for category, authentication, transport, and verification.
- `Sort by` for default, popular, trending, new, and alphabetical.
- Two-column responsive cards with real logo, name, publisher, description,
  auth label, tool count/state, last catalog update, and Connect action.
- Details view with source, endpoint, documentation, categories, tools,
  descriptions, and `Connect <product>`.
- Installed view with `CONNECTED`, `AUTHENTICATION REQUIRED`, `SYNCING`,
  `FAILED`, and `DISCONNECTED` states plus refresh, inspect, and disconnect.
- No raw URL, command, custom header, stdio, or manual OAuth mode controls.

**Acceptance:** UI renders only API records, never vendor constants. Loading,
empty, stale, error, and authentication-required states are distinct. Mobile
and desktop layouts preserve the existing AverQel theme.

## Phase 6: DeepSpace Tool Safety

**Why:** Connecting a Google service is not enough; tool exposure and action
execution must remain permissioned and auditable.

**Files and areas:**

- `backend/app/services/integrations/mcp_runtime.py`
- existing DeepSpace tool registration/execution services
- `backend/app/models/integrations/mcp_server.py`
- `backend/tests/integration/`

**Work:**

1. Namespace tools by server identity without trusting display names.
2. Validate arguments against the stored live schema.
3. Apply read/write/send/delete approval rules before execution.
4. Bind execution to the requesting tenant, user, and connected server.
5. Persist redacted audit events and tool revision information.

**Acceptance:** A user cannot invoke a disabled, stale, unauthorized, or
cross-tenant tool. Approval and audit behavior remains compatible with existing
agents and connectors.

## Phase 7: Verification and Test Gates

**Backend tests:**

- Approved-only marketplace visibility.
- Google source, publisher, endpoint, logo, auth, and documentation fields.
- Search, category/auth/transport filters, sort, and pagination.
- OAuth state, PKCE, callback binding, scope enforcement, token encryption,
  expiry, revocation, and tenant isolation.
- Real catalog tool count, tool descriptions, schemas, pagination, stale and
  pending states.
- Refresh persistence for `mcp_catalog_tool_count` and
  `mcp_catalog_last_sync_at`.
- Connect, refresh, inspect, disconnect, and failure recovery.
- SSRF, redirect, log redaction, and permission checks.

**Frontend tests:**

- Real catalog-driven Google cards and logos.
- Search, `Filter by`, `Sort by`, empty, loading, and error states.
- Details content and generated Connect label.
- Authentication-required versus connected states.
- Installed status badge, tool count, and last sync rendering.
- No raw endpoint/header/stdio controls in the normal user UI.

**Live smoke test:** Use a dedicated test Google account and approved test
endpoint. Do not place personal credentials in fixtures, logs, CI variables,
or documentation.

## Phase 8: Local and VPS Release

**Why:** Local and production must use the same catalog contract and security
behavior without copying secrets into images or source control.

**Files and areas:**

- `backend/.env` and `backend/.env.localprod` secret references only
- `backend/ops/caddy/Caddyfile`
- `backend/ops/caddy/Caddyfile.localprod`
- deployment manifests and worker/scheduler configuration
- release and smoke-test documentation

**Release gates:**

1. Apply and verify reversible migrations.
2. Configure Google OAuth secrets in the local and VPS secret stores.
3. Verify callback URLs, HTTPS, Caddy routing, worker, and scheduler paths.
4. Run API, frontend, worker, and live smoke tests.
5. Confirm user-visible catalog count and approved records in both environments.
6. Roll back without deleting tenant connections or encrypted tokens.

## Must Not Break

- Existing authentication, tenant isolation, RLS, encryption, and OAuth
  callback behavior.
- Existing connector integrations and DeepSpace tool permissions.
- Existing worker queues, scheduled jobs, audit events, and catalog refreshes.
- Existing installed-server refresh, inspect, disconnect, and status handling.
- Local and VPS routing, Caddy configuration, and API proxy behavior.

## Approval Gate

This document is a design and implementation plan, not a claim that Google
Workspace is already implemented. Before coding begins, approve the following
scope:

- Google Workspace only.
- Official remote MCP records only.
- Approved catalog data only in the user marketplace.
- Generic/dynamic OAuth with deployment-managed client credentials where the
  official server requires them.
- Real post-connect catalog discovery.
- No stdio, community, arbitrary endpoint, or arbitrary header UI.

After approval, implementation starts at Phase 0 and proceeds one phase at a
time with test evidence before the next phase.
