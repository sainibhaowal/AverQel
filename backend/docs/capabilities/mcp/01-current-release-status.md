# AverQel MCP: current implementation and release status

**Status:** implemented in the local codebase; deployment and provider-specific
OAuth credentials remain environment gates.

This file summarizes repository behavior. Check the
[current worktree and release index](../../release/03-current-worktree-change-index.md)
for migration and deployment evidence before treating a connector as ready in
a specific environment.

This document is a concise status summary. The implementation contract is
maintained in [`06-mcp-connections.md`](../06-mcp-connections.md), and
operational procedures are in the
[DeepSpace operations runbook](../../deepspace/05-deepspace-operations-runbook.md).

## What AverQel provides

AverQel provides a curated MCP marketplace and a tenant/user-scoped MCP
runtime. A user can inspect an approved connector, authorize it when the
required provider credentials are configured, review its tools and policy, and
make approved tools available to DeepSpace.

The runtime path is:

```text
approved catalog entry
  -> connection/OAuth policy
  -> encrypted tenant/user credential
  -> catalog and tool-policy refresh
  -> DeepSpace broker
  -> approval/policy checks
  -> remote tool call and safe result
```

## Current implementation

- Approved MCP catalog and provider metadata.
- Remote streamable HTTP transport with supported SSE fallback; HTTPS endpoint
  validation rejects unsafe or restricted destinations.
- OAuth and encrypted credential storage for supported provider profiles.
- Tenant and user ownership checks on connections, tools, and tokens.
- Marketplace, provider details, Inspector, connection, refresh, disconnect,
  and tool-policy UI.
- Read-only policy mode and explicit approval for side-effecting tools.
- DeepSpace broker operations for just-in-time tool search, schema loading,
  and tool execution.
- Bounded tool schemas and result previews; the model does not receive the
  complete private catalog or OAuth material.
- Durable audit and health metadata without exposing secret values.

## Current API surface

The MCP router is mounted under `/api/v1/mcp`. The implemented surface
includes:

- approved marketplace/catalog listing and marketplace facets;
- marketplace-entry connection creation;
- tenant/user-owned server listing, details, refresh, disconnect, and Inspector;
- OAuth start, callback, and disconnect for supported provider profiles;
- server and tool policy reads/updates;
- conversation and DeepSpace-scoped connection overrides.

The runtime does not expose an arbitrary endpoint-registration route. New
connections must originate from an approved catalog entry and pass endpoint,
ownership, policy, and credential checks.

## Deliberate boundaries

The following are not supported by this release:

- arbitrary user-entered MCP endpoints;
- local `stdio`, SSH, or arbitrary local-process servers;
- vendor repository cloning or execution;
- arbitrary VPS command execution;
- tenant-wide or global provider tokens;
- side-effecting calls that bypass approval, ownership, risk, or freshness
  checks.

The legacy connector path remains separate. Adding an MCP connector must not
replace provider routing, authentication, encryption, or DeepSpace queue
behavior.

## Security contract

Every connection is bound to:

```text
tenant_id + user_id + approved provider/server identity
```

Before a tool is exposed or called, the backend checks:

1. connection enabled and owned by the authenticated tenant/user;
2. catalog identity and freshness;
3. server and tool policy;
4. read-only restrictions;
5. approval requirements and risk limits;
6. tenant-safe result handling and audit recording.

Tokens, refresh tokens, client secrets, PKCE data, raw endpoint configuration,
and encrypted credential payloads are never returned to the frontend, prompt,
model, or logs.

## Release verification

The MCP implementation is covered by the current backend/frontend regression
checks and focused MCP broker, bridge, policy, ownership, OAuth, and UI tests.
Local code verification does not prove that an external provider can be used:
each provider still needs valid deployment credentials and a provider-specific
live smoke test.

The OpenZen free-tier restriction is unrelated to MCP. It is an upstream model
provider policy and cannot be bypassed by the MCP runtime.

## Source of truth

For current implementation details, use:

- [`06-mcp-connections.md`](../06-mcp-connections.md)
- [`05-deepspace-operations-runbook.md`](../../deepspace/05-deepspace-operations-runbook.md)
- [`01-end-to-end-handoff.md`](../../release/01-end-to-end-handoff.md)

This status document does not claim that every external MCP provider is live
or that VPS deployment has been completed.
