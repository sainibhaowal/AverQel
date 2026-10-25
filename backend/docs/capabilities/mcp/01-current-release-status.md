# AverQel MCP: current implementation and release status

**Status:** Composio-hosted app catalog and account-scoped connection flow are
implemented locally. Each user must supply a Composio project key; OAuth apps
also require a correctly configured public callback origin. This source status
does not prove those requirements are met in a particular deployment.

This file summarizes repository behavior. Check the
[current worktree and release index](../../release/03-current-worktree-change-index.md)
for migration and deployment evidence before treating a connector as ready in
a specific environment.

This document is a concise status summary. The implementation contract is
maintained in [`06-mcp-connections.md`](../06-mcp-connections.md), and
operational procedures are in the
[DeepSpace operations runbook](../../deepspace/05-deepspace-operations-runbook.md).

## What AverQel provides

AverQel provides a live Composio app catalog and a tenant/user-scoped MCP
runtime. Each user supplies their own Composio project key, inspects an app and
its tools, connects their own external account where authorization is required,
and makes the resulting tools available to DeepSpace under the saved policy.
The catalog comes from Composio and can change; a listing does not guarantee
that an app is enabled for a particular project.

The runtime path is:

```text
user-owned Composio project key
  -> live Composio catalog
  -> user connects a selected app
  -> account-owned hosted session and tool catalog
  -> DeepSpace broker
  -> approval/policy checks
  -> remote tool call and safe result
```

## Current implementation

- Live Composio toolkit and tool metadata.
- Remote streamable HTTP transport with supported SSE fallback; HTTPS endpoint
  validation rejects unsafe or restricted destinations.
- Per-user Composio project-key storage encrypted with the connector-secret
  backend; Composio hosted-session identifiers are also encrypted and scoped.
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

- per-user Composio key status, validation, save, and removal;
- paginated Composio toolkit and tool catalog listing and details;
- Composio hosted app connection and callback completion;
- tenant/user-owned server listing, details, refresh, disconnect, and Inspector;
- server and tool policy reads/updates;
- conversation and DeepSpace-scoped connection overrides.

The runtime does not expose an arbitrary endpoint-registration route. The
Marketplace does not use AverQel's former bundled Google, GitHub, Notion, and
Slack cards; existing installed connection records are retained. OAuth app
connections require the public AverQel callback origin, and each connected app
is bound to the AverQel account that started it.

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

Composio project keys, hosted-session identifiers, provider tokens where
applicable, raw endpoint configuration, and encrypted credential payloads are
never returned to the frontend, prompt, model, or logs. The running backend
decrypts the user's Composio key when making provider requests; it is encrypted
at rest, not end-to-end encrypted from the server.

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
