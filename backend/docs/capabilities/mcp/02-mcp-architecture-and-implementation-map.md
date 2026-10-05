# MCP architecture and implementation map

**Status:** implementation-map snapshot; source inspection recorded on 2026-09-23.

This document is the source-grounded implementation map for AverQel MCP. It
describes the implementation observed at that inspection date, where it was
implemented, what DeepSpace used, and which boundaries were intentional.
Check the current source and the [release index](../../release/03-current-worktree-change-index.md)
before using this snapshot to make a release decision.

## 1. Product contract

AverQel currently uses a curated, approved remote MCP catalog.

The supported user flow is:

~~~text
AverQel MCP marketplace
  -> reviewed approved catalog entry
  -> user selects Connect
  -> provider-specific OAuth or configured authorization
  -> encrypted tenant/user token storage
  -> catalog refresh
  -> user reviews policy and tool permissions
  -> conversation or DeepSpace scope is attached
  -> DeepSpace discovers a bounded tool reference
  -> policy and approval checks run
  -> remote MCP tool executes
  -> bounded result and durable audit event return
~~~

The system is designed so that a connected MCP service is optional. Normal
DeepSpace chat, provider selection, queue behavior, authentication, and
conversation behavior continue without an MCP connection.

## 2. What is implemented

The repository contains the following implementation areas:

- Curated official MCP provider metadata.
- Database-backed registry entries with trust and catalog status.
- Tenant/user-owned MCP server records.
- Encrypted MCP OAuth token records.
- Single-use OAuth transaction state.
- Durable MCP event records with per-server sequence values.
- Streamable HTTP transport.
- Supported SSE transport and initialization fallback.
- OAuth discovery and callback handling for configured provider profiles.
- Encrypted token refresh persistence.
- Catalog discovery for tools, prompts, resources, and resource templates.
- Pagination for tool discovery.
- Schema normalization and catalog revision tracking.
- Background catalog refresh workers.
- Lifecycle monitoring and reconnect/backoff through Celery retries.
- Tool and catalog change notifications.
- Tenant and user ownership checks.
- Server, connection, and tool policy controls.
- Risk classification for read, write, delete, and external-message actions.
- Approval gates for side-effecting tools.
- DeepSpace bridge integration.
- Bounded model-facing MCP tool broker.
- Marketplace, provider details, Inspector, connection, refresh, disconnect,
  and policy UI.
- Durable audit and health metadata without returning secret values.
- Cross-user and cross-tenant security tests.

## 3. Exact code map

### Catalog and trust

- backend/app/integrations/catalog/mcp_official_providers.py
  - Code-reviewed provider metadata.
  - Public documentation, support, privacy, scopes, risk labels, and trusted
    local logo keys.
  - No OAuth client secrets, access tokens, or live secret material.
- backend/app/integrations/services/mcp_catalog_service.py
  - Idempotently upserts the curated catalog source.
- backend/app/integrations/workers/tasks_mcp_catalog.py
  - Runs scheduled curated-catalog synchronization.
- backend/app/integrations/services/mcp_endpoint_security.py
  - Requires HTTPS and rejects credentials embedded in URLs.
  - Resolves the hostname and rejects restricted, private, loopback, link-local,
    multicast, reserved, and unspecified addresses.
- backend/app/integrations/api/mcp.py
  - Marketplace queries require approved catalog entries.
  - The API does not expose arbitrary endpoint registration.

### Durable models and migrations

- backend/app/integrations/models/mcp_server.py
  - MCPServer: tenant/user-owned server and lifecycle state.
  - MCPRegistryEntry: catalog and trust metadata.
  - MCPOAuthTransaction: single-use OAuth state.
  - MCPEvent: durable lifecycle/catalog/audit event sequence.
  - MCPOAuthToken: encrypted OAuth credential material.
- backend/app/integrations/models/mcp_connection_policy.py
  - Server-level risk ceiling, default mode, approval rules, and tool modes.
- Relevant migration family:
  - 20260716_0001_mcp_runtime_tables.py
  - 20260716_0002_mcp_event_sequence.py
  - 20260716_0003_declarative_connector_oauth.py
  - 20260716_0004_seed_connector_oauth_metadata.py
  - 20260717_0003_mcp_registry_catalog.py
  - 20260720_0001_mcp_catalog_governance.py
  - 20260720_0002_clear_unapproved_mcp_registry.py
  - 20260722_0001_mcp_oauth_transactions.py
  - 20260722_0002_mcp_privacy_scrub.py
  - 20260722_0003_mcp_provider_metadata.py
  - 20260722_0004_mcp_connection_policies.py
  - 20260723_0005_mcp_granted_scopes.py
  - 20260803_0001_mcp_auto_attach_connected_accounts.py
  - 20260818_0001_mcp_master_tool_mode.py

Migration files describe the schema history. They do not prove that a
particular local, staging, or VPS database has been upgraded; that requires
running Alembic against the selected database.

### Runtime and credentials

- backend/app/integrations/services/mcp_runtime.py
  - Builds the MCP runtime from an approved server record.
  - Supports Streamable HTTP and SSE.
  - Uses the installed MCP SDK for protocol sessions.
  - Loads encrypted token material only for the runtime lifetime.
  - Persists refreshed OAuth tokens back through encrypted storage.
  - Normalizes tool schemas and serializes bounded results.
  - Classifies failures and identifies when reconnection is required.
- backend/app/integrations/services/mcp_oauth_service.py
  - OAuth discovery, state, callback, and provider authorization flow.
- backend/app/integrations/services/connector_secret_crypto.py
  - Existing authenticated encryption boundary for connector secrets.
- backend/app/integrations/repositories/mcp_events.py
  - Durable event append and ordered event reads.
- backend/app/integrations/workers/tasks_mcp.py
  - Refreshes tools and optional catalog surfaces.
  - Stores catalog counts, sync time, cache, and revision.
  - Receives list-changed notifications.
  - Runs a short lifecycle lease and uses Celery retry backoff after failures.

### DeepSpace integration

- backend/app/deepspace/services/mcp_bridge.py
  - Selects only enabled, connected, tenant-owned, user-owned servers.
  - Applies catalog freshness, ownership, policy, risk, and approval checks.
  - Namespaces tools to prevent collisions.
  - Requests refresh without blocking ordinary chat when a cached catalog ages.
- backend/app/deepspace/services/mcp_tool_broker.py
  - Keeps the complete private catalog server-side.
  - Exposes bounded search, schema, call, and result continuation operations.
  - Prevents OAuth values, transport configuration, and full private schemas
    from entering model context.
- backend/app/deepspace/services/mcp_result_store.py
  - Supports bounded result continuation without placing oversized raw output
    into the model context.

### API and frontend

- backend/app/integrations/api/mcp.py
  - Marketplace, connection, OAuth, policy, scoped connection, refresh,
    disconnect, and Inspector routes under /api/v1/mcp.
- frontend/app/dashboard/mcp/
  - Marketplace, provider details, connection status, policy controls,
    Inspector, and connection-scope UI.
- frontend/lib/mcp-api.ts
  - Frontend API contracts and safe marketplace URL handling.
- frontend/app/dashboard/deepspace/
  - DeepSpace consumes the existing broker/bridge path; MCP does not replace
    the chat stream or queue.

## 4. Runtime behavior

### Connect

1. The user views an approved marketplace entry.
2. The API validates that the entry is approved and connectable.
3. OAuth starts with validated state and provider metadata when required.
4. The callback validates the state and stores encrypted token material.
5. The server record is tenant/user-owned and the policy record is created.
6. A catalog refresh discovers tools and optional prompts/resources.
7. The UI shows status, health, catalog metadata, and policy controls.

### Discover

1. DeepSpace queries the bridge for connected servers belonging to the current
   tenant and user.
2. The bridge checks enabled status, approval, ownership, policy, and catalog
   state.
3. The broker returns only compact matching references.
4. The model requests one bounded schema only when needed.
5. The private bridge retains the exact server/tool binding and catalog revision.

### Execute

1. The model sends an exact broker tool reference and arguments.
2. The bridge resolves that reference to the authorized server and raw tool.
3. Input and tool policy checks run before the remote call.
4. Read actions may run automatically when policy permits.
5. Write, delete, and external-message actions require the existing approval
   gate unless an explicit policy allows them.
6. The remote result is bounded, serialized, audited, and returned to DeepSpace.
7. OAuth refresh failures are classified as reconnect-required without exposing
   token material.

### Refresh and recover

1. Scheduled workers refresh enabled server catalogs.
2. Tool, prompt, or resource list-change notifications create durable events.
3. A catalog refresh is scheduled after a list-change notification.
4. Lifecycle workers hold a short session lease to receive notifications.
5. Worker failure persists status and retry count.
6. Celery retries with bounded exponential backoff.
7. A worker restart can resume the lifecycle through the scheduled task path.

## 5. Security and isolation contract

Every generic MCP server is bound to:

~~~text
tenant_id + user_id + approved provider/server identity
~~~

The implementation must preserve:

- authenticated tenant and user ownership;
- database tenant context and RLS boundaries;
- encrypted credentials and token payloads;
- no secret values in frontend payloads, model context, logs, or audit text;
- approval and risk controls for side effects;
- HTTPS and restricted-network endpoint rejection;
- bounded schemas, arguments, remote results, and model exposure;
- durable audit/event records;
- catalog approval and freshness checks.

The legacy connector path remains separate. Adding or refreshing MCP servers
must not replace provider routing, authentication, encryption, DeepSpace queue
ordering, SSE behavior, or normal chat execution.

## 6. Deliberate product boundaries

These are intentionally not part of the current release:

- arbitrary user-entered MCP endpoint registration;
- unrestricted public community-server installation;
- local stdio process execution;
- SSH or arbitrary local-process execution;
- vendor repository cloning or package execution;
- arbitrary VPS command execution;
- global or tenant-wide credentials;
- side-effecting calls that bypass policy or approval;
- a claim that every external provider is live without provider credentials and
  a provider-specific smoke test.

These boundaries are security decisions, not unfinished code by default.

## 7. Tests and verification locations

Backend MCP tests include:

- tests/integration/test_mcp_api.py
- tests/integration/test_mcp_catalog_service.py
- tests/integration/test_mcp_marketplace_catalog.py
- tests/integration/test_mcp_oauth_flows.py
- tests/integration/test_mcp_phase2_schema.py
- tests/integration/test_mcp_phase4_api.py
- tests/integration/test_mcp_phase5_policy.py
- tests/integration/test_mcp_provider_oauth.py
- tests/security/test_mcp_cross_user_access.py
- tests/security/test_mcp_oauth_secrets.py
- tests/security/test_mcp_tenant_isolation.py
- tests/security/test_mcp_tool_policy.py
- tests/unit/test_deepspace_mcp_bridge.py
- tests/unit/test_mcp_catalog_service.py
- tests/unit/test_mcp_catalog_worker.py
- tests/unit/test_mcp_connection_policy.py
- tests/unit/test_mcp_official_providers.py
- tests/unit/test_mcp_provider_auth.py
- tests/unit/test_mcp_runtime.py
- tests/unit/test_mcp_security.py
- tests/unit/test_mcp_tool_broker.py
- tests/unit/test_mcp_worker_runtime.py

Frontend MCP tests cover marketplace cards, marketplace pages, provider details,
OAuth state, connection controls, policies, Inspector, scoped connections, and
documentation pages.

A test file existing in the repository is evidence of coverage intent. It is
not a claim that the test passed in every environment. Record fresh test output
for release decisions.

## 8. Historical asset assessment

The file assets/ruff work.md is a 470-line ignored historical transcript. It
is not Ruff configuration and is not read by the application.

### Relevant information worth preserving

- The distinction between an MCP SDK and a complete application runtime.
- The need for encrypted OAuth storage and refresh persistence.
- Tenant/user ownership and audit events.
- Dynamic catalog discovery and DeepSpace tool exposure.
- SSRF protection for remote endpoints.
- The danger of running arbitrary stdio processes in the API host.
- The need for provider-specific OAuth credentials and live smoke tests.

Those points are now represented more accurately in this document and the
companion MCP status/contract documents.

### Information that is obsolete or misleading

- The claim that AverQel only has the SDK and a partial runtime.
- The old list saying SSE, token persistence, reconnect workers, catalog
  workers, Inspector, or marketplace APIs are all missing.
- The old “six predefined connector mappings” description as the current MCP
  marketplace contract.
- The proposal to enable arbitrary public registry/community-server execution.
- Old local database credential errors and old test availability statements.
- Any historical “not 100% complete” status without a date and environment.

## 9. Disposition of the historical asset

Do not use assets/ruff work.md as current documentation.

The clean production documentation choice is:

1. Keep this new document and the canonical MCP status documents under
   backend/docs.
2. If historical conversation context is not needed, delete the ignored asset
   after confirming that no audit record depends on it.
3. If history is valuable, move or copy it to an explicitly named archive such
   as backend/docs/archive/mcp-architecture-history.md and label it
   Historical, not current status.
4. Do not leave it named ruff work.md.

No application behavior depends on that asset, and renaming or removing it will
not change MCP, DeepSpace, chat, authentication, storage, or database behavior.
