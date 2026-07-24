# AverQel MCP Plan and Release Status

Last reviewed: 2026-07-24

This is the authoritative MCP status document. Read sections 1 and 7 first.

## 1. Current status

### Implemented and verified

~~~text
[DONE] Phase 1  Curated remote provider catalog
[DONE] Phase 2  Database metadata and connection policies
[DONE] Phase 3  Google/GitHub provider OAuth profiles
[DONE] Phase 4  API routes, DTOs, ownership checks, and redaction
[DONE] Phase 5  Runtime and DeepSpace policy enforcement
[DONE] Phase 6  Frontend marketplace and connection controls
[DONE] Phase 7  Documentation and complete MCP test matrix
~~~

### Automated verification passed

~~~text
[PASS] Backend full pytest suite
[PASS] Frontend full Vitest suite: 83 files, 256 tests
[PASS] TypeScript check
[PASS] ESLint
[PASS] Ruff
[PASS] Git diff validation
[PASS] Exact backend and frontend MCP test paths
[PASS] OAuth, tenant isolation, secret-redaction, and policy tests
[PASS] Marketplace, provider-detail, Inspector, policy, and scope UI tests
~~~

## 2. What AverQel provides

AverQel is a secure MCP host/client and curated marketplace. It connects to
approved remote vendor MCP servers. It does not clone or execute vendor MCP
repositories.

User flow:

~~~text
Marketplace
  → provider details
  → review transport, tools, risks, scopes, and health
  → Connect
  → provider OAuth consent screen
  → AverQel callback
  → encrypted per-user connection
  → Inspector and policy configuration
  → DeepSpace planning and execution
~~~

The marketplace displays provider identity, Official/Community status, badges,
trusted logo, transport, authentication, tools, categories, scopes, links,
health, and Connect/Reconnect actions.

The Inspector displays safe connected-account labels, status, catalog
freshness, granted scopes, health, reconnect/disconnect, tool permissions,
read-only mode, risk settings, and conversation/DeepSpace enablement.

## 3. Security and architecture

### Remote-only release

Supported:

~~~text
streamable_http
approved remote SSE/HTTP where the runtime supports it safely
~~~

Intentionally unsupported:

~~~text
stdio servers
SSH servers
local-process servers
arbitrary user-entered endpoints
arbitrary VPS command execution
vendor repository cloning or execution
~~~

### Identity and isolation

Every connection and token is bound to:

~~~text
tenant_id
user_id
provider/server identity
~~~

DeepSpace loads only the current tenant/user connections. Ownership and policy
are checked before planning and immediately before a remote call. AverQel never
uses a tenant-wide or global Google/GitHub token.

### OAuth and secrets

- Google and GitHub use reviewed static provider profiles.
- PKCE and signed, single-use OAuth state are used.
- OAuth transactions and token payloads are encrypted.
- The existing encrypted token payload format is preserved.
- Granted scope names and safe account identity may be shown to the owner.
- Disconnect removes local encrypted credentials and attempts provider
  revocation where supported.
- Scope changes require reauthorization.
- Tokens, refresh tokens, client secrets, PKCE data, and raw OAuth metadata
  never enter MCPServer.config, frontend DTOs, logs, prompts, or MCP events.

### Tool-policy precedence

~~~text
1. Disabled/revoked provider or connection       → deny
2. Tenant/user/server ownership mismatch         → deny
3. Missing/stale conversation or DeepSpace gate  → deny
4. Explicitly Blocked tool                      → deny
5. Read-only mode for writes/deletes/messages    → deny
6. Risk ceiling exceeded                        → deny
7. Stale catalog or removed tool                 → deny
8. Needs approval                               → require confirmation
9. Always allow                                 → run after all checks pass
~~~

Always allow never bypasses platform, tenant, ownership, risk, freshness, or
confirmation rules. Blocked tools are not offered to DeepSpace.

## 4. Completed implementation

### Phase 1 — Curated provider catalog

Status: implemented and verified.

~~~text
backend/app/integrations/catalog/__init__.py
backend/app/integrations/catalog/mcp_official_providers.py
backend/app/integrations/services/mcp_catalog_service.py
backend/app/integrations/workers/tasks_mcp_catalog.py
backend/scripts/seed_mcp_catalog.py
~~~

Initial catalog entries:

~~~text
google-gmail
google-drive
google-calendar
google-chat
google-people
github
~~~

The catalog includes provider identity, publisher class, endpoint, transport,
OAuth profile, scopes, products, risk policy, badges, trusted logo, tool
categories, and safe health metadata. Sync is idempotent and source-scoped.

### Phase 2 — Database and policies

Status: implemented and verified.

~~~text
backend/alembic/versions/20260722_0003_mcp_provider_metadata.py
backend/alembic/versions/20260722_0004_mcp_connection_policies.py
backend/app/integrations/models/mcp_connection_policy.py
backend/app/integrations/models/mcp_server.py
backend/app/platform/database/model_registry.py
~~~

The schema stores provider identity, health, catalog revision, account
identity, encrypted-token identity, and tenant/user policy. Defaults are
conservative: disabled scope overrides, read-only mode, and explicit
always_allow, needs_approval, or blocked modes.

### Phase 3 — OAuth profiles

Status: implemented and verified.

~~~text
backend/app/integrations/services/mcp_provider_auth.py
backend/app/integrations/services/mcp_oauth_service.py
backend/app/integrations/services/connector_oauth_service.py
backend/app/core/config.py
backend/.env.example
backend/.env.vps.example
backend/.env.localprod.example
~~~

Deployment settings:

~~~text
MCP_GOOGLE_OAUTH_CLIENT_ID
MCP_GOOGLE_OAUTH_CLIENT_SECRET
MCP_GITHUB_OAUTH_CLIENT_ID
MCP_GITHUB_OAUTH_CLIENT_SECRET
MCP_OAUTH_REDIRECT_URI
~~~

These settings remain separate from legacy connector OAuth.

### Phase 4 — API

Status: implemented and verified.

Implementation:

~~~text
backend/app/integrations/api/mcp.py
~~~

Routes:

~~~text
GET  /api/v1/mcp/marketplace
GET  /api/v1/mcp/marketplace/{entry_id}
POST /api/v1/mcp/marketplace/{entry_id}/connect
GET  /api/v1/mcp/servers
GET  /api/v1/mcp/servers/{server_id}
DELETE /api/v1/mcp/servers/{server_id}
GET  /api/v1/mcp/servers/{server_id}/policy
PUT  /api/v1/mcp/servers/{server_id}/policy
GET  /api/v1/mcp/servers/{server_id}/tools
PUT  /api/v1/mcp/servers/{server_id}/tools/{tool_name}/policy
GET  /api/v1/mcp/deepspaces/{deepspace_id}/connections
PUT  /api/v1/mcp/deepspaces/{deepspace_id}/connections/{server_id}
GET  /api/v1/mcp/conversations/{conversation_id}/connections
PUT  /api/v1/mcp/conversations/{conversation_id}/connections/{server_id}
POST /api/v1/mcp/servers/{server_id}/refresh
POST /api/v1/mcp/servers/{server_id}/oauth/start
GET  /api/v1/mcp/oauth/callback
GET  /api/v1/mcp/servers/{server_id}/oauth/callback
GET  /api/v1/mcp/servers/{server_id}/inspector
~~~

All responses use explicit DTOs. Catalog administration requires
mcp:catalog:manage. Approved Community providers remain distinguishable and
may connect when reviewed readiness permits. Raw config, probe errors, OAuth
material, and raw events are never returned.

### Phase 5 — Runtime and DeepSpace enforcement

Status: implemented and verified.

~~~text
backend/app/integrations/services/mcp_runtime.py
backend/app/integrations/workers/tasks_mcp.py
backend/app/deepspace/execution/agent_executor.py
backend/app/deepspace/execution/agent_tools.py
backend/app/deepspace/execution/tool_contracts.py
backend/app/deepspace/execution/agent_permissions.py
~~~

Dynamic tools carry provider/server/tenant/user identity, original name,
catalog revision, risk level, and approval requirement. The legacy connector
path remains unchanged.

### Phase 6 — Frontend marketplace and controls

Status: implemented and verified.

~~~text
frontend/app/dashboard/mcp/page.tsx
frontend/app/dashboard/mcp/inspector/[id]/page.tsx
frontend/lib/mcp-api.ts
frontend/app/dashboard/mcp/providers/[entryId]/page.tsx
frontend/app/dashboard/mcp/_components/MCPMarketplaceCard.tsx
frontend/app/dashboard/mcp/_components/MCPProviderDetails.tsx
frontend/app/dashboard/mcp/_components/MCPConnectionPolicyPanel.tsx
frontend/app/dashboard/mcp/_components/MCPToolPermissionTable.tsx
frontend/app/dashboard/mcp/_components/MCPConnectionScopePanel.tsx
frontend/app/dashboard/mcp/_components/MCPCommunityWarning.tsx
frontend/app/dashboard/mcp/_components/MCPHealthStatus.tsx
frontend/public/mcp/google.svg
frontend/public/mcp/github.svg
~~~

The old details modal was retired after the API-backed detail route was linked
from every card. Trusted local logo keys are used; the browser does not probe
endpoints or discover arbitrary metadata.

### Phase 7 — Documentation

Status: implemented and verified.

~~~text
frontend/app/documentation/connectors-mcp/page.tsx
frontend/app/documentation/privacy-security/page.tsx
frontend/app/documentation/providers/page.tsx
frontend/README.md
Docs/mcp-plan.md
~~~

The documentation explains provider trust, OAuth, isolation, policy precedence,
remote transport, limitations, badges, and why vendor servers are not cloned.

## 5. Complete test matrix

### Backend unit

~~~text
backend/tests/unit/test_mcp_catalog_service.py
backend/tests/unit/test_mcp_provider_auth.py
backend/tests/unit/test_mcp_connection_policy.py
backend/tests/unit/test_mcp_runtime.py
backend/tests/unit/test_mcp_security.py
~~~

### Backend integration and security

~~~text
backend/tests/integration/test_mcp_api.py
backend/tests/integration/test_mcp_oauth_flows.py
backend/tests/integration/test_mcp_marketplace_catalog.py
backend/tests/integration/test_mcp_connection_policy.py
backend/tests/security/test_mcp_tenant_isolation.py
backend/tests/security/test_mcp_oauth_secrets.py
backend/tests/security/test_mcp_tool_policy.py
backend/tests/security/test_mcp_cross_user_access.py
~~~

These verify unapproved-provider rejection, Community visibility, tenant/user
isolation, OAuth replay/error/secret handling, scope reauthorization,
deny-first policy, read-only and approval behavior, stale catalogs, provider
health gates, and legacy connector preservation.

### Frontend

~~~text
frontend/tests/mcp-page.test.ts
frontend/tests/mcp-page.render.test.tsx
frontend/tests/mcp-provider-details.test.tsx
frontend/tests/mcp-connection-policy.test.tsx
frontend/tests/mcp-oauth-state.test.tsx
frontend/tests/mcp-inspector.test.tsx
frontend/tests/mcp-marketplace-card.test.tsx
frontend/tests/mcp-provider-detail-page.test.tsx
frontend/tests/mcp-tool-permission-table.test.tsx
frontend/tests/mcp-connection-scope-panel.test.tsx
~~~

These verify marketplace rendering, provider details, trusted logos, OAuth
boundary behavior, Inspector data, policy controls, tool modes, and explicit
conversation/DeepSpace scope controls.

## 6. Compatibility requirements

These must remain true:

- Existing MCPServer rows and encrypted OAuth payloads remain valid.
- Existing MCP and legacy connector routes remain available.
- Google Drive/GitHub legacy connector integrations remain separate from native
  MCP OAuth settings.
- Tenant RLS and tenant/user ownership checks remain active.
- Endpoint validation, stale-catalog protection, no-retry behavior, DeepSpace
  confirmation, event redaction, and catalog jobs remain active.
- Frontend filters, installed connections, Inspector deep links, and
  provider-neutral catalog rendering remain compatible.
- No browser or API response exposes credentials, raw config, raw events, or
  arbitrary remote resources.

## 7. Remaining release operations

These are the only current TODOs:

~~~text
[ ] Configure VPS MCP OAuth credentials.
[ ] Configure the production callback URL.
[ ] Run staging Google OAuth with staging credentials.
[ ] Run staging GitHub OAuth with staging credentials.
[ ] Run staging Gmail-read DeepSpace smoke test.
[ ] Run staging GitHub-read DeepSpace smoke test.
[ ] Run staging write-action confirmation test.
[ ] Review provider scopes, consent screens, health, and catalog monitoring.
~~~

Real credentials belong only in deployment secret storage. They must never be
placed in source, tests, documentation, logs, prompts, configuration JSON,
frontend responses, or MCP events.

## 8. Explicitly out of scope

~~~text
stdio MCP servers
SSH MCP servers
local-process execution
arbitrary user-entered remote endpoints
arbitrary VPS command execution
cloning vendor MCP repositories
automatic approval of unreviewed Community providers
~~~

Future providers and transports require a separate catalog entry, security
review, OAuth profile where applicable, endpoint policy review, and tests before
they become connectable.
