
I inspected the current AverQel MCP implementation. Phases 1 through 7 are
implemented in the current `main` branch. This document is the implementation
plan and release record; future provider onboarding and live staging OAuth
verification remain operational follow-up work, not unimplemented product
phases.

The correct decision is:

- Do not clone `taylorwilsdon/google_workspace_mcp` for the official marketplace.
- Do not build a separate MCP server for every vendor.
- AverQel should act as the secure MCP host/client and marketplace.
- AverQel connects directly to official remote vendor MCP endpoints.
- Community/self-hosted MCP servers can be added later as a separate trust category.

Google’s official remote MCP endpoints are documented here: [Google Workspace MCP documentation](https://developers.google.com/workspace/guides/configure-mcp-servers). GitHub also hosts an official remote MCP server at `https://api.githubcopilot.com/mcp/`; see [GitHub’s official MCP server](https://github.com/github/github-mcp-server).

## Scope decision: remote marketplace connectors only

This project will implement an AverQel-curated marketplace for **remote MCP
servers**. AverQel is the secure MCP client/host: it stores the approved
connector metadata, completes OAuth for the current tenant and user, obtains
the remote tool catalog, and routes authorized DeepSpace calls to that remote
server.

The supported production transports for this release are:

```text
streamable_http
SSE / HTTP only when the remote provider is explicitly approved and the runtime
supports it safely
```

The following are deliberately out of scope for this release:

```text
Cloning or running vendor MCP repositories inside AverQel
Local stdio MCP servers
SSH MCP servers
Arbitrary user-entered endpoints
Arbitrary command execution on the VPS
Unreviewed marketplace entries becoming connectable
```

This scope is intentional. It avoids turning the AverQel VPS into an execution
host for third-party code and allows endpoint validation, OAuth, tenant
isolation, health monitoring, policy enforcement, and incident response to be
applied consistently. Future community connectors may still be remote services,
but they must pass a separate review and carry a prominent community warning.

## 1. What AverQel already has

### Marketplace and provider metadata

Existing model:

[backend/app/integrations/models/mcp_server.py](/home/ravi/Projects/AverQel/backend/app/integrations/models/mcp_server.py:35)

`MCPRegistryEntry` already supports:

- Vendor/display name
- Publisher
- Description
- Transport
- Remote URL
- OAuth metadata
- Categories
- Official/verified flags
- Logo URL
- Tool count
- Tool previews
- Documentation metadata
- Trust status
- Catalog status
- Verification source

Existing marketplace routes are in:

[backend/app/integrations/api/mcp.py](/home/ravi/Projects/AverQel/backend/app/integrations/api/mcp.py:239)

Current marketplace routes include:

```text
GET  /api/v1/mcp/marketplace
GET  /api/v1/mcp/marketplace/facets
GET  /api/v1/mcp/catalog
POST /api/v1/mcp/catalog/{entry_id}/review
POST /api/v1/mcp/marketplace/{entry_id}/connect
```

Only approved remote entries are publicly returned.

### Tenant/user MCP connections

Existing model:

[backend/app/integrations/models/mcp_server.py](/home/ravi/Projects/AverQel/backend/app/integrations/models/mcp_server.py:15)

`MCPServer` already stores:

- `tenant_id`
- `user_id`
- Server status
- Transport
- Enabled state
- Remote URL inside controlled configuration
- Catalog cache
- Connection errors
- Reconnect state

Existing routes:

```text
GET    /api/v1/mcp/servers
POST   /api/v1/mcp/servers/{server_id}/refresh
DELETE /api/v1/mcp/servers/{server_id}
GET    /api/v1/mcp/servers/{server_id}/inspector
```

### OAuth and encryption

Existing encrypted models:

```text
mcp_oauth_transactions
mcp_oauth_tokens
```

OAuth service:

[backend/app/integrations/services/mcp_oauth_service.py](/home/ravi/Projects/AverQel/backend/app/integrations/services/mcp_oauth_service.py:16)

Current protections include:

- Encrypted PKCE state
- Encrypted OAuth client metadata
- Encrypted access/refresh tokens
- Single-use OAuth transactions
- Tenant/user/server ownership checks
- OAuth state validation
- No OAuth secrets returned to the frontend

Existing routes:

```text
POST /api/v1/mcp/servers/{server_id}/oauth/start
GET  /api/v1/mcp/servers/{server_id}/oauth/callback
```

### Runtime and DeepSpace

Existing runtime:

[backend/app/integrations/services/mcp_runtime.py](/home/ravi/Projects/AverQel/backend/app/integrations/services/mcp_runtime.py:167)

Existing DeepSpace MCP integration:

[backend/app/deepspace/execution/agent_executor.py](/home/ravi/Projects/AverQel/backend/app/deepspace/execution/agent_executor.py:850)

DeepSpace already:

- Loads only the current tenant’s and current user’s MCP servers
- Requires the connection to be enabled
- Requires status `connected`
- Requires a fresh catalog
- Dynamically exposes MCP tools
- Checks the server again during execution
- Prevents stale or unknown tools
- Uses confirmation tiers for risky tools

The frontend marketplace already exists:

[frontend/app/dashboard/mcp/page.tsx](/home/ravi/Projects/AverQel/frontend/app/dashboard/mcp/page.tsx:1)

The Inspector already exists:

[frontend/app/dashboard/mcp/inspector/[id]/page.tsx](/home/ravi/Projects/AverQel/frontend/app/dashboard/mcp/inspector/[id]/page.tsx:1)

### Current marketplace foundation, expressed as the user experience

The current marketplace foundation already provides or has fields for:

- Cards and a two-column desktop grid
- Logo support
- Official and verified status
- Description, publisher, category, tool count, tool preview, and remote URL
- OAuth/authentication label and Connect action
- Marketplace filtering and sorting
- Installed connections and an inspector route
- Documentation URL and catalog/verification metadata

The next implementation must retain these working paths while expanding them
into the complete connector experience below. This is an expansion of the
current marketplace, not a replacement with hard-coded provider screens.

## 2. What is currently missing

### A. Official provider catalog data

The marketplace database exists, but official providers are not yet fully seeded as curated AverQel providers.

We need initial approved records for:

```text
Google Gmail MCP
Google Drive MCP
Google Calendar MCP
Google Chat MCP
Google People MCP
GitHub MCP
```

Google currently documents these remote endpoints:

```text
https://gmailmcp.googleapis.com/mcp/v1
https://drivemcp.googleapis.com/mcp/v1
https://calendarmcp.googleapis.com/mcp/v1
https://chatmcp.googleapis.com/mcp/v1
https://people.googleapis.com/mcp/v1
```

GitHub’s official remote endpoint is:

```text
https://api.githubcopilot.com/mcp/
```

The marketplace also needs explicit fields for:

- Provider slug
- Official/community classification
- Version
- Documentation URL
- Health status
- Last health check
- Requested OAuth scopes
- Supported products
- Tool risk classification
- OAuth client profile
- Verification source

### B. Provider identity is currently hidden in JSON

Currently, the connection stores the registry entry through:

```text
config["registry_entry_id"]
```

This is weaker than a real database relationship.

We need a proper provider relationship while preserving the existing JSON configuration for backward compatibility.

### C. Static OAuth configuration for Google and GitHub

The current generic MCP OAuth flow relies heavily on discovery and dynamic registration.

Official Google and GitHub SaaS OAuth flows require AverQel to behave as a registered OAuth client. We need:

```text
AverQel OAuth client ID
AverQel OAuth client secret where required
Stable AverQel callback URL
Provider-specific allowed scopes
```

The client secret must never be stored in `MCPServer.config` and never be sent to the browser.

### D. Stable OAuth callback

The current callback contains the server ID:

```text
/mcp/servers/{server_id}/oauth/callback
```

For Google/GitHub OAuth applications, a stable callback is safer and easier to register:

```text
GET /api/v1/mcp/oauth/callback
```

The signed OAuth state will identify the correct tenant, user and server.

The existing callback must remain available for backward compatibility.

### E. Connection tool policies

The current runtime uses a heuristic based on tool names:

```text
create/update/delete/send/upload/modify → confirmation
```

That is useful as a fallback, but it is not enough for a marketplace.

Each connection needs a policy containing:

```text
allowed_tools
denied_tools
read_only
maximum_risk_level
require_confirmation_for_writes
require_confirmation_for_external_messages
allow_file_access
allow_sharing_changes
```

The policy must be checked:

1. When tools are added to DeepSpace.
2. Before every tool call.
3. After catalog refresh.
4. After reconnection.
5. When a user changes the policy.

### F. UI does not show all marketplace information

The existing UI shows basic provider details, but it needs to show:

- Official/community badge
- Verified status
- Vendor
- Version
- Health status
- Endpoint
- Transport
- Authentication type
- Requested OAuth scopes
- Supported products
- Risk levels
- Tool permissions
- Documentation
- Last verification time
- Last health check
- Connection account
- Read-only/approval policy

### G. The marketplace needs a complete connector experience, not a basic modal

The current marketplace cards are already two-column on desktop, but the
details are shown in a basic client-side modal. The production requirement is a
full connector detail route with a stable URL. The marketplace must clearly
distinguish the connector's identity, trust level, capabilities, health, and
the controls granted by the current user.

The completed user experience must include:

- Polished two-column responsive cards, with an accessible one-column mobile
  layout
- `Official`, `Community`, `New`, and `Trending` badges when the catalog data
  supports them; no badge may be inferred from the display name
- An optional `Interactive` capability badge only for reviewed connectors that
  genuinely support interactive/approval-driven workflows
- Author/publisher name and author website
- Documentation, support, and privacy-policy links, each validated and opened
  safely as an external link
- A full connector detail page, rather than only a modal
- Connector URL display with a copy action; URLs must be treated as data, not
  HTML, and the page must never expose credentials or OAuth metadata
- Tool categories, tool descriptions, and read/write/delete/external-message
  risk labels
- A clear community-connector warning explaining that it is not an AverQel
  official connector and that the user should review the provider and scopes
- Safe health status and last-verified/last-health-check timestamps. Health
  checks must not reveal account data, tokens, tool results, or internal error
  details
- Trusted local provider logos for curated providers, with a safe text/avatar
  fallback. Remote arbitrary logo URLs must not be blindly trusted

After a user connects a provider, the installed-connection experience must
show:

- The connected account identity (for example, the consented email address),
  only to that account's tenant/user and only when the provider returns it
- Connection state, approved scopes, catalog freshness, last safe health result,
  and the provider's public identity
- Reconnect, refresh catalog, inspect tools, and disconnect/revoke controls
- Per-tool permissions: `Always allow`, `Needs approval`, and `Blocked`
- Per-conversation or per-DeepSpace enable/disable controls. A disabled
  connection or tool must be excluded from planning and blocked again at tool
  execution time
- A read-only mode that prevents all non-read tools, even if an old tool cache
  says they are available

None of these controls are security theater: the selected setting must be
persisted under the current tenant/user/server, returned by a safe API DTO, and
enforced by DeepSpace immediately before a remote call.

## 3. Production implementation plan

### Phase 1: Curated provider catalog

Status: **implemented**. The implementation is catalog-driven and includes a
temporary connection-readiness gate: all six official entries are visible, but
they cannot start generic MCP OAuth until Phase 3 installs and verifies a
provider-specific OAuth profile. This prevents a seeded provider from using an
unreviewed dynamic OAuth registration flow.

Add:

```text
backend/app/integrations/catalog/__init__.py
backend/app/integrations/catalog/mcp_official_providers.py
backend/app/integrations/services/mcp_catalog_service.py
backend/app/integrations/workers/tasks_mcp_catalog.py
backend/scripts/seed_mcp_catalog.py
```

These files will contain only curated provider metadata, not vendor credentials.

Initial entries:

```text
google-gmail
google-drive
google-calendar
google-chat
google-people
github
```

Each entry will include:

```python
{
    "provider_slug": "google-gmail",
    "publisher": "Google",
    "publisher_type": "official",
    "official": True,
    "verified": True,
    "remote_url": "https://gmailmcp.googleapis.com/mcp/v1",
    "transport": "streamable_http",
    "auth_type": "oauth",
    "documentation_url": "...",
    "requested_scopes": [...],
    "supported_products": ["Gmail"],
    "risk_policy": {...},
}
```

The curated schema and seed source will additionally provide the metadata
needed to render the marketplace without provider-specific frontend branches:

```text
author_name, author_website_url
documentation_url, support_url, privacy_policy_url
badge flags: official, community, new, trending, interactive
trusted_logo_key (served from AverQel static assets for curated providers)
tool categories and per-tool risk classification
safe health status and last health/verification timestamps
```

`New`, `Trending`, and `Interactive` are catalog attributes with explicit
review criteria and expiry/review dates; they are not hard-coded labels. A
provider is `community` when it is reviewed but is neither the official vendor
nor published/operated by AverQel. Only `trust_status=approved` entries can be
connected.

Community servers will be supported later but will never automatically receive the official badge.

Phase 1 implementation files:

```text
backend/app/integrations/catalog/__init__.py
backend/app/integrations/catalog/mcp_official_providers.py
backend/app/integrations/services/mcp_catalog_service.py
backend/app/integrations/workers/tasks_mcp_catalog.py
backend/scripts/seed_mcp_catalog.py
```

The catalog is seeded idempotently at API startup and by the scheduled
maintenance task. It only writes its own global source namespace, never deletes
other registry rows, and never touches tenant connections, OAuth tables, or MCP
events. The existing marketplace API exposes safe catalog metadata and the
existing card UI shows `Setup pending` for a non-ready provider.

### Phase 2: Database improvements

Status: **implemented and verified**.

This phase is additive and production-safe: existing server rows remain valid,
legacy manual servers keep nullable catalog/policy links, existing encrypted
OAuth ciphertext/nonce/key-id columns are unchanged, and policy rows are not
created automatically until the later runtime-policy phase wires enforcement.

Add a migration after the current head:

```text
backend/alembic/versions/20260722_0003_mcp_provider_metadata.py
backend/alembic/versions/20260722_0004_mcp_connection_policies.py
```

Changes to `MCPRegistryEntry`:

- Provider slug
- Publisher type
- Version
- Documentation URL
- Health status
- Health check timestamp
- Requested scopes
- Supported products
- Risk policy
- OAuth profile
- Author website, support URL, and privacy-policy URL
- Explicit publisher class (`official` or `community`) and catalog badge data
- Trusted logo key rather than relying solely on arbitrary external image URLs
- Tool category/risk summary and safe health metadata

Changes to `MCPServer`:

- Real registry/provider foreign key
- Explicit provider identity
- Account identity metadata
- Connection policy reference
- Catalog revision metadata

Add a new model:

```text
backend/app/integrations/models/mcp_connection_policy.py
```

The policy table will be:

```text
mcp_connection_policies
```

It will include:

- `tenant_id`
- `user_id`
- `server_id`
- Allowed tools
- Denied tools
- Read-only setting
- Risk ceiling
- Approval rules
- Per-tool mode: `always_allow`, `needs_approval`, or `blocked`
- Per-DeepSpace and per-conversation enablement overrides with a conservative
  default of disabled when an override is absent or stale
- Created/updated timestamps

It will use tenant RLS like the existing MCP tables.

Strengthen `MCPOAuthToken` with explicit user/provider identity while preserving the current encrypted payload format.

Implementation notes:

- `MCPServer.registry_entry_id` and `MCPOAuthToken.registry_entry_id` are real
  foreign keys with safe `SET NULL` behavior when a global catalog row is
  retired.
- Existing OAuth token rows are backfilled from their tenant-owned server and
  receive a required `user_id`; token reads and writes now require the server's
  tenant and user identity together.
- `MCPConnectionPolicy` uses tenant RLS with `FORCE ROW LEVEL SECURITY`, one
  policy per server, `read_only=true`, `default_enabled=false`, and stale or
  missing overrides treated as disabled by the later evaluator.
- Marketplace APIs prefer the normalized metadata columns and continue to
  sanitize legacy JSON metadata before returning it.
- No Phase 2 API route changes policy behavior yet; policy enforcement belongs
  to the runtime-policy phase so existing valid connections are not silently
  disabled during this schema rollout.

### Phase 3: OAuth provider profiles

Status: **implemented and verified**.

Add:

```text
backend/app/integrations/services/mcp_provider_auth.py
```

Update:

```text
backend/app/integrations/services/mcp_oauth_service.py
backend/app/integrations/services/connector_oauth_service.py
backend/app/core/config.py
backend/.env.example
backend/.env.vps.example
backend/.env.localprod.example
```

Add dedicated settings:

```text
MCP_GOOGLE_OAUTH_CLIENT_ID
MCP_GOOGLE_OAUTH_CLIENT_SECRET
MCP_GITHUB_OAUTH_CLIENT_ID
MCP_GITHUB_OAUTH_CLIENT_SECRET
MCP_OAUTH_REDIRECT_URI
```

These will remain separate from existing connector OAuth settings to avoid breaking current Google Drive/GitHub integrations.

The OAuth service will support:

- Static vendor OAuth client configuration
- PKCE
- Signed state
- Stable callback
- Per-user/per-tenant token storage
- Scope verification
- Account identity capture
- Token refresh
- Reauthorization
- Disconnect/revocation where supported

No OAuth credentials will enter:

```text
MCPServer.config
frontend responses
logs
MCP events
DeepSpace prompts
```

Implementation notes:

- Curated Google Workspace and GitHub entries use fixed, code-reviewed OAuth
  endpoints and static client credentials from dedicated `AKS_MCP_*` settings.
- PKCE verifiers and OAuth client metadata are encrypted in
  `mcp_oauth_transactions`; they are never placed in `MCPServer.config`.
- The stable callback is `/api/v1/mcp/oauth/callback`; its server, tenant, and
  user are resolved only from signed state and tenant-scoped database queries.
- Returned scopes are checked against the provider profile before tokens are
  stored. Account identity is reduced to safe labels such as provider subject,
  account ID, email, and display name.
- Token refresh preserves the encrypted provider metadata needed for future
  refreshes. Disconnect attempts provider revocation where supported, removes
  local encrypted credentials, and clears account identity.
- Existing connector OAuth continues using only `AKS_CONNECTOR_*` settings and
  its existing `ConnectorSecret` storage.

### Phase 4: API changes

Update:

[backend/app/integrations/api/mcp.py](/home/ravi/Projects/AverQel/backend/app/integrations/api/mcp.py:99)

Preserve all existing routes and add or extend:

```text
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

GET /api/v1/mcp/servers/{server_id}/inspector
```

Admin-only catalog operations remain protected by:

```text
mcp:catalog:manage
```

The current connection endpoint incorrectly describes connections as only “official verified” entries. It should allow any AverQel-approved entry while keeping official/community status visible.

All API responses must use explicit marketplace, connection, and policy DTOs.
They must never expose `MCPServer.config` wholesale, raw endpoint probe errors,
OAuth transaction data, access tokens, refresh tokens, client secrets, or raw
MCP event payloads. The new per-conversation/per-DeepSpace endpoints must
verify that the referenced conversation/DeepSpace belongs to the current
tenant and that the current user may operate it before reading or changing an
override.

Phase 4 implementation notes:

- Marketplace list, detail, facets, connection, installed-server, policy,
  tool-policy, scoped override, refresh, OAuth, and Inspector routes now use
  explicit response DTOs.
- Marketplace visibility is limited to AverQel-approved remote entries, while
  connection eligibility is provider-neutral: approved community entries remain
  distinguishable and may connect when their reviewed readiness metadata allows
  it.
- Server responses retain only the catalog/tool metadata needed by the current
  UI. Configuration is allowlisted, endpoint/provider errors are generalized,
  and account identity is reduced to safe labels. OAuth material and raw event
  payloads are never returned.
- Scoped connection reads and writes require exact tenant/user ownership of the
  referenced Conversation or durable DeepSpace mission snapshot. Missing or
  stale overrides resolve to disabled.
- Tenant context is restored after commits before ORM refresh/serialization so
  PostgreSQL RLS remains active throughout the request lifecycle.

### Phase 5: Runtime and DeepSpace policy enforcement

Status: **implemented and verified**.

Update:

```text
backend/app/integrations/services/mcp_runtime.py
backend/app/integrations/workers/tasks_mcp.py
backend/app/deepspace/execution/agent_executor.py
backend/app/deepspace/execution/agent_tools.py
backend/app/deepspace/execution/tool_contracts.py
backend/app/deepspace/execution/agent_permissions.py
```

Every dynamic tool will carry:

```text
provider_id
server_id
tenant_id
user_id
original_tool_name
catalog_revision
risk_level
approval_requirement
```

DeepSpace will:

- Load only the current user’s connections.
- Filter tools through the connection policy.
- Preserve current freshness checks.
- Preserve current confirmation behavior.
- Recheck ownership and policy before execution.
- Reject provider-disabled or revoked connections.
- Reject tools removed from the latest catalog.
- Never use another user’s OAuth token.
- Never use a tenant-wide global Google/GitHub token.
- Enforce connection, tool, conversation, and DeepSpace enablement as a deny
  condition before planning and immediately before a remote call.
- Apply `blocked` before any other policy, then read-only and risk rules, then
  `needs_approval`; `always_allow` cannot bypass a global tenant or platform
  safety rule.

The existing legacy connector path will remain unchanged and will not be deleted.

Phase 5 implementation notes:

- Native dynamic tools are admitted to DeepSpace only when the current
  tenant/user owns the connection, the provider remains AverQel-approved, the
  catalog is fresh, the connection policy is enabled, and the current
  conversation (plus durable DeepSpace mission when present) has an explicit
  enabled override.
- The same deny-first evaluator runs during tool discovery and again before the
  remote call. It enforces allow/deny lists, per-tool mode, read-only mode, risk
  ceilings, approval rules, provider identity, and catalog revision.
- Remote writes/deletes/messages cannot be made automatically by changing an
  `always_allow` setting; platform confirmation remains authoritative.
- Refreshed or revoked provider identities cannot build a runtime, and token
  queries remain bound to the exact server, tenant, user, and provider.
- Legacy connector-backed MCP calls continue through their existing
  `ConnectorSecret` path and are not routed through native MCP connection
  policies.

### Phase 6: Frontend marketplace and connection controls

Update:

```text
frontend/app/dashboard/mcp/page.tsx
frontend/app/dashboard/mcp/inspector/[id]/page.tsx
frontend/lib/mcp-api.ts
```

Add:

```text
frontend/app/dashboard/mcp/providers/[entryId]/page.tsx
frontend/app/dashboard/mcp/_components/MCPMarketplaceCard.tsx
frontend/app/dashboard/mcp/_components/MCPProviderDetails.tsx
frontend/app/dashboard/mcp/_components/MCPConnectionPolicyPanel.tsx
frontend/app/dashboard/mcp/_components/MCPToolPermissionTable.tsx
frontend/app/dashboard/mcp/_components/MCPConnectionScopePanel.tsx
frontend/app/dashboard/mcp/_components/MCPCommunityWarning.tsx
frontend/app/dashboard/mcp/_components/MCPHealthStatus.tsx
```

Add local trusted logos:

```text
frontend/public/mcp/google.svg
frontend/public/mcp/github.svg
```

The existing details modal will be retired only after the new detail route is
complete, linked from every card, and covered by tests. The old card click
behavior may redirect to that route during the transition; it must not create a
second inconsistent source of provider data.

The marketplace list page will render the following from API data:

```text
Two-column cards (desktop), one column (small screens)
Local trusted logo, name, short description, publisher
Official / Community / New / Trending / Interactive badges when applicable
Authentication and transport label
Tool count and concise tool preview
Safe health/last-verified indicator
View details and Connect/Reconnect action
```

The full connector detail page will render:

```text
Provider header, publisher and author website
Official/community trust explanation and community warning when applicable
Description, supported products, categories, connector URL, transport, version
Documentation, support, and privacy links
Requested OAuth scopes before consent
Tool list with category, description, and read/write/delete/external-message labels
Safe health and verification status
Connect or Reconnect action
```

The installed connection and inspector pages will render:

```text
Connected account (only when safely available to its owner)
Connection status, catalog freshness, scopes, safe health, reconnect/disconnect
Tool permission table: Always allow / Needs approval / Blocked
Read-only setting and explicit high-risk approval settings
Per-conversation and per-DeepSpace enable/disable controls
An explanation that a blocked or disabled tool will not be offered to DeepSpace
```

The UI must use server-provided trusted-logo keys for curated assets. If a
community entry has a logo URL, it must pass the existing URL security policy
and be rendered with a safe fallback; UI rendering must not fetch arbitrary
metadata or perform browser-side endpoint health probes.

The user will see:

```text
Google Gmail
Official · Verified
Remote HTTP · OAuth
Read email, search threads, create drafts
Requested scopes
Risk: read / write
Connect
```

After clicking Connect:

```text
Connect
→ Google/GitHub authorization
→ return to AverQel
→ show connected account
→ refresh catalog
→ display available tools
→ configure policy
```

The frontend will never receive access tokens, refresh tokens, client secrets or raw OAuth metadata.

### Phase 7: Documentation

Update:

```text
frontend/app/documentation/connectors-mcp/page.tsx
frontend/app/documentation/privacy-security/page.tsx
frontend/app/documentation/providers/page.tsx
frontend/README.md
```

Document:

- Official versus community MCP providers
- OAuth consent behavior
- Tenant/user isolation
- Tool permission policies
- Read-only mode
- Approval requirements
- How Google/GitHub connections work
- Why AverQel does not clone vendor MCP servers
- Token storage and revocation behavior
- Provider preview/health limitations
- What the remote transport label means and why stdio/SSH/local servers are
  not supported in this release
- The meaning of Official, Community, New, Trending, and Interactive badges
- The meaning and precedence of Always allow, Needs approval, Blocked,
  read-only, conversation, and DeepSpace controls

## 4. Tests required

Backend unit tests:

```text
backend/tests/unit/test_mcp_catalog_service.py
backend/tests/unit/test_mcp_provider_auth.py
backend/tests/unit/test_mcp_connection_policy.py
backend/tests/unit/test_mcp_runtime.py
backend/tests/unit/test_mcp_security.py
```

Backend integration/security tests:

```text
backend/tests/integration/test_mcp_api.py
backend/tests/integration/test_mcp_oauth_flows.py
backend/tests/integration/test_mcp_marketplace_catalog.py
backend/tests/integration/test_mcp_connection_policy.py
backend/tests/security/test_mcp_tenant_isolation.py
backend/tests/security/test_mcp_oauth_secrets.py
backend/tests/security/test_mcp_tool_policy.py
backend/tests/security/test_mcp_cross_user_access.py
```

Tests must verify:

- Unapproved providers cannot connect.
- Community providers are visibly distinguished.
- One tenant cannot see another tenant’s marketplace connection.
- One user cannot use another user’s token.
- OAuth state replay fails.
- OAuth callback errors do not leak secrets.
- OAuth tokens never appear in configuration or events.
- Scope changes require reauthorization.
- Policy blocks denied tools.
- Read-only mode blocks write tools.
- Delete/send/share tools require confirmation.
- Stale catalogs cannot execute.
- Provider health failures do not expose tools.
- Existing legacy connectors still work.

Frontend tests:

```text
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
```

## 5. What must not break

We will preserve:

- Existing `MCPServer` records
- Existing `/mcp` routes
- Existing encrypted OAuth token format
- Existing tenant RLS
- Existing OAuth transaction protections
- Existing endpoint validation
- Existing no-retry behavior for side-effecting tools
- Existing stale catalog protection
- Existing DeepSpace approval system
- Existing connector OAuth flows
- Existing Google Drive/GitHub connector integrations
- Existing frontend marketplace filters
- Existing Inspector behavior
- Existing Celery catalog refresh jobs
- Existing MCP event redaction
- Existing migrations and rollback safety
- Existing card-grid filters, installed connection list, Inspector route, and
  all valid deep links while the full detail page is introduced
- Provider-neutral frontend architecture: Google, GitHub, and future vendors
  must be catalog data, not one-off hard-coded UI implementations
- No browser access to token material, raw runtime events, or arbitrary remote
  connector resources

No vendor repository will be cloned into AverQel during this implementation.

## 6. Verification and release gate

Before completion:

```text
alembic upgrade head
alembic check
backend full test suite
frontend full test suite
TypeScript check
Ruff
ESLint
migration review
cross-tenant security tests
staging Google OAuth test
staging GitHub OAuth test
DeepSpace Gmail read test
DeepSpace GitHub repository read test
write-action confirmation test
token-redaction review
detail-page and card accessibility review
community-warning and badge review
per-tool/per-conversation/per-DeepSpace policy enforcement tests
safe-logo and external-link validation tests
```

Real Google/GitHub credentials will not be placed in tests or committed files. Live OAuth testing will use a staging Google Cloud project and staging GitHub OAuth/GitHub App configuration.

Only after all verification succeeds will I create the commit and release tag.

Phase 5 runtime and DeepSpace policy enforcement is complete and released as
`averqel-mcp-phase5-20260723`.

## 7. Phase 6 frontend marketplace and connection controls

Phase 6 is complete. The exact implementation files verified for this phase
are:

```text
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
```

The exact Phase 6 frontend test files are:

```text
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
```

These files were verified as present and included in the frontend test run.
Phase 6 is implemented with one typed API boundary in
`frontend/lib/mcp-api.ts`. The marketplace remains catalog/API-driven and now
uses a two-column responsive card grid, trusted local Google/GitHub logo keys,
official/community/New/Trending/Interactive badges, transport/auth labels,
safe health timestamps, and route links to
`/dashboard/mcp/providers/{entryId}`. The old details modal was retired.

Provider details render the safe publisher/author links, community warning,
connector URL, transport, version, categories, the complete reviewed tool
catalog, requested OAuth scopes, and backend health/verification status.
Community logo URLs are server-validated and use a local fallback when unsafe.
External links are limited to plain HTTP(S) URLs; no browser-side endpoint or
metadata probes are performed.

The installed connection inspector now renders safe account identity labels,
connection health, catalog revision/freshness, reconnect/disconnect/refresh
controls, policy settings, read-only and risk ceilings, per-tool
`always_allow`/`needs_approval`/`blocked` controls, granted OAuth scope names,
and explicit conversation/DeepSpace scope controls. OAuth return parameters
automatically open the Installed view and are removed from browser history.
Tokens, secrets, OAuth metadata, raw config, and raw event payloads remain
unavailable to the frontend.

Verified OAuth scope names are stored in the non-secret `granted_scopes`
column added by migration `20260723_0005`; the encrypted credential payload
format is unchanged. The provider detail route and callback return behavior
are covered by frontend tests, while backend tests cover scope persistence and
secret redaction.

Phase 6 verification:

```text
frontend full test suite: verified after Phase 6 completion changes
MCP frontend tests: verified after Phase 6 completion changes
TypeScript check: passed
focused ESLint: 0 errors
focused backend MCP schema/API/OAuth tests: verified after Phase 6 completion changes
```

The version field was added as an optional marketplace DTO field because the
database already stored it but the prior API response did not expose it. The
full `tools` field was added separately from `tool_preview` so list-card
compatibility is preserved while provider details have an explicit complete
reviewed catalog contract.

## Phase 6 post-OAuth and active-context UX

After OAuth succeeds, the marketplace now redirects directly to the connected
server inspector instead of stopping at the Installed list. The inspector
shows the safe account identity, refreshed tool catalog, granted scope names,
and policy controls immediately.

DeepSpace stores the currently active conversation identifier in browser-owned
short-lived context state. The MCP inspector reads that context and loads the
conversation scope automatically. No Gmail, GitHub, OAuth, or credential data
is stored in this context. The backend still validates tenant/user ownership
and requires an explicit enable decision because absent or stale overrides
remain disabled by design.

## Phase 7 documentation and complete test matrix

Phase 7 documentation is complete. The user-facing documentation now explains:

- Official versus Community providers and the Official, Community, New,
  Trending, and Interactive badges.
- OAuth consent, PKCE, encrypted token storage, revocation, scope changes,
  and the `Setup pending` operator configuration state.
- Tenant/user isolation, read-only mode, approval requirements, and the
  precedence of `Always allow`, `Needs approval`, and `Blocked`.
- Remote HTTP/SSE transport and why stdio, SSH, local processes, arbitrary
  endpoints, and vendor repository cloning are not supported in this release.
- Safe provider health/preview limitations and the fact that tokens, secrets,
  raw OAuth metadata, and raw MCP events are never returned to the frontend.
- How Google and GitHub connections work through approved remote MCP servers.

Updated documentation files:

```text
frontend/app/documentation/connectors-mcp/page.tsx
frontend/app/documentation/privacy-security/page.tsx
frontend/app/documentation/providers/page.tsx
frontend/README.md
```

The complete MCP test matrix is present under the exact requested paths:

```text
backend/tests/unit/test_mcp_catalog_service.py
backend/tests/unit/test_mcp_provider_auth.py
backend/tests/unit/test_mcp_connection_policy.py
backend/tests/unit/test_mcp_runtime.py
backend/tests/unit/test_mcp_security.py

backend/tests/integration/test_mcp_api.py
backend/tests/integration/test_mcp_oauth_flows.py
backend/tests/integration/test_mcp_marketplace_catalog.py
backend/tests/integration/test_mcp_connection_policy.py
backend/tests/security/test_mcp_tenant_isolation.py
backend/tests/security/test_mcp_oauth_secrets.py
backend/tests/security/test_mcp_tool_policy.py
backend/tests/security/test_mcp_cross_user_access.py

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
```

The tests cover rejected/unapproved providers, visible Community status,
tenant and user isolation, OAuth state and secret handling, token/event
redaction, scope and reauthorization boundaries, denied/read-only/risky tool
policy, stale catalogs, provider health gates, and preservation of the legacy
connector path. Frontend coverage verifies the marketplace, provider details,
OAuth boundary, inspector, cards, policy controls, tool permissions, and
conversation/DeepSpace scope controls.

Phase 7 verification completed:

```text
backend full pytest suite: passed
frontend full Vitest suite: passed (83 files, 256 tests)
frontend TypeScript check: passed
frontend ESLint: passed
backend Ruff: passed
git diff validation: passed
```

The test suite uses mocked OAuth/provider responses and never stores real
Google or GitHub credentials. Live staging OAuth checks remain a release
operator task requiring staging credentials and are intentionally not run in
CI or committed to the repository.

The test coverage was committed and pushed as:

```text
cd73c9f56 test(mcp): complete end-to-end coverage
```
