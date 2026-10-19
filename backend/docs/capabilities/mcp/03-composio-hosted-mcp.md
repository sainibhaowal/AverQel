# Composio hosted MCP apps

**Status:** implemented in source; a deployment still needs administrator
configuration and a live provider smoke test.

This document covers the optional Composio app catalog, available from the
Providers screen's **MCP Apps** shortcut or Dashboard → MCP Marketplace →
**Composio Apps**. It is separate from the existing AverQel MCP
marketplace and its six curated categories. It does not replace existing
providers.

Composio maintains the remote native toolkit catalog. AverQel reads that live
catalog through the pinned Python SDK (`composio==0.28.0`) and paginates both
toolkits and tools. The displayed total comes from Composio's API; users can
search and load every returned page. Catalog contents and counts can change;
there is no fixed 250-app promise. Catalog entries are supplied by Composio and are not
individually represented as AverQel-reviewed providers.

## 1. Deployment prerequisites

1. Create a Composio project for the AverQel deployment and a project API key.
   The key must permit toolkit/tool catalog reads, session management, and
   session-linked tool execution. Composio scoped keys may require both
   **Session management** and **Session tool execution** permissions. See
   [Composio API key permissions](https://docs.composio.dev/docs/configuring-sessions#api-key-permissions).
2. Configure AverQel's connector-secret encryption backend and active key. The
   same configured backend protects the Composio project key and hosted session
   identifiers. Keep encryption keys outside source control and retain old key
   IDs during the supported rotation window.
3. For OAuth apps, set `AVERQEL_PUBLIC_ORIGIN` to the deployment's canonical
   HTTPS origin. Toolkits Composio marks as requiring no account authorization
   can be added without this callback setup.
4. For OAuth apps, in the Composio project dashboard, set the callback verifier URL to the
   callback displayed in the Composio Apps tab:
   `https://<averqel-host>/dashboard/mcp/composio/callback`.
5. For OAuth apps, set `COMPOSIO_CALLBACK_VERIFIER_ENABLED=true` in the AverQel backend
   environment only after the Composio callback verifier is configured and
   reachable. Restart/redeploy the backend through the deployment's normal
   change process so the setting is loaded.
6. Apply the Alembic migration that creates the platform-scoped encrypted
   `composio_credentials` singleton.
7. Sign in as the allowlisted platform administrator with required MFA and
   open Providers → **MCP Apps** (or MCP Marketplace → **Composio Apps**) to
   save the project API key. AverQel verifies that
   the key can read the catalog before saving it. The key is never returned to
   the frontend.

The exact callback verifier setup is specific to Composio's hosted Connect
flow. The URL passed to `session.authorize` is not a substitute for setting the
project-level callback verifier. See
[Composio connected-account callback verification](https://docs.composio.dev/reference/api-reference/connected-accounts)
and [sessions over MCP](https://docs.composio.dev/docs/sessions-via-mcp).

## 2. User connection flow

1. An authenticated user opens Providers → **MCP Apps** or **Composio Apps** in
   MCP Marketplace. Existing
   marketplace categories and installed MCP connections remain available in
   their existing tabs.
2. The browser asks AverQel for the current toolkit page and uses Composio's
   search, category, and cursor APIs. The backend returns public app/tool
   metadata only.
3. The user can inspect tool names, descriptions, risk labels, and input fields
   before starting a connection. Toolkit details are cursor-paginated; use
   **Load more tools** when a toolkit has more than one page.
4. On Connect, AverQel creates a Composio session for one toolkit and for the
   stable identity `averqel:<tenant UUID>:<user UUID>`. For apps that require
   authorization, the browser is sent to Composio's HTTPS hosted authorization
   flow. The Composio project API key stays on the server.
5. Composio redirects OAuth apps to the configured verifier with a one-time `session_uri`.
   The callback page removes it from the browser URL and submits it through the
   authenticated API. Composio verifies the session against the same stable
   AverQel user ID. An authorization started by one AverQel account cannot be
   completed while signed in as another.
6. Toolkits marked as not requiring authorization skip OAuth and queue catalog
   discovery immediately. After OAuth verification, AverQel stores the
   connection under the user's tenant and account and queues the same catalog
   refresh. The installed connection then appears in DeepSpace through the
   existing MCP bridge and broker.

Composio's catalog contains different authentication schemes. Many apps use
hosted OAuth; some can require additional provider-specific setup, or may not
support a user-facing OAuth flow. The marketplace shows the schemes Composio
returns, and a failed/unsupported authorization is reported without exposing
provider credentials. Do not promise one-click OAuth for every toolkit.

## 3. API and storage boundaries

| Route or record | Purpose and access |
| --- | --- |
| `GET /api/v1/mcp/composio/status` | Authenticated catalog setup and callback status; contains no secret. |
| `GET /api/v1/mcp/composio/toolkits` | Live, paginated Composio toolkit metadata. |
| `GET /api/v1/mcp/composio/toolkits/{slug}` | Live, paginated tool metadata and bounded input schemas. |
| `POST /api/v1/mcp/composio/toolkits/{slug}/connect` | Starts a toolkit-limited authorization session for the caller. |
| `POST /api/v1/mcp/composio/oauth/complete` | Completes the one-time callback for the authenticated caller. |
| `GET/PUT/DELETE /api/v1/admin/providers/composio` | Allowlisted platform-admin and MFA-protected key status, set, and removal. Mutations are audited. |
| `composio_credentials` | One platform-level project key, encrypted with the configured connector-secret backend and `composio:platform` associated data. RLS permits access only under the platform bypass context used by the service. |
| `mcp_servers` | One user's provider state; the hosted session ID is encrypted with tenant, user, and server IDs as associated data. Public DTOs omit session and header credentials. |

The user ID sent to Composio is a derived AverQel UUID identity, not the user's
email address. The platform key is shared as a server-side integration
credential, while Composio connections and AverQel server records remain
scoped to the authenticated user and tenant. A change to or removal of the
platform key disconnects existing Composio sessions and clears their cached
catalogs so those accounts must reconnect.

## 4. DeepSpace execution and approval

The connected Composio MCP endpoint is created with the Composio direct-tools
preset and only the selected toolkit. The regular MCP worker discovers its live
tool catalog. DeepSpace does not receive the entire catalog in its initial
prompt: its existing broker returns bounded references, retrieves one schema
when requested, validates the selected binding and arguments, and routes
execution through the existing MCP policy evaluator and approval card.

New Composio policies allow reads under the existing read policy. Tool risk is
classified from Composio labels and action names; unknown actions default to
`write`. Writes, deletes, and external messages require user approval before
the remote call. Setting a side-effecting tool to **Always allow** does not
remove the runtime's mandatory approval requirement. Users can lower a risk
ceiling or block individual actions. Risk labels are conservative heuristics,
not a guarantee that a third-party tool is safe; users should inspect the
provider, requested account scopes, arguments, and approval details.

The MCP client validates the Composio endpoint as HTTPS, requires the expected
Composio host, rejects redirects and restricted IP destinations, and forwards
only the session headers returned by the Composio SDK. The session ID and
authorization headers are server-side only. API responses, browser state,
audit descriptions, and model tool references must not contain the platform
key, session URI, session ID, OAuth tokens, or Composio session headers.

## 5. Data processing and privacy

Using a Composio app sends the selected tool's inputs and outputs through
Composio's hosted service and to the connected app provider. Composio manages
the provider authentication and connected-account token lifecycle for this
integration; AverQel receives a verified connected-account identifier and an
encrypted hosted-session identifier, not the provider password or OAuth token.
Users must review the scopes shown by the provider and the current Composio and
connected-provider privacy terms before authorizing an app. The service
operator must list Composio and the actual connected suppliers in the hosted
deployment's subprocessor disclosure and set retention/transfer terms with
those suppliers. Do not describe this flow as end-to-end encrypted from
Composio or the connected app provider.

The current integration does not create a second AverQel copy of provider
OAuth tokens. Disconnecting or deleting an AverQel user removes the local MCP
server and encrypted local session identifier through existing account cleanup;
the operator must confirm that the Composio connected account is revoked or
deleted as part of that user's vendor-side data-retention process. The source
does not assert that Composio has deleted remote data or backups.

## 6. Operating and troubleshooting

- **Catalog unavailable:** verify project key validity, Composio API
  availability, outbound HTTPS/DNS, and catalog-read permission. Key errors are
  deliberately redacted in API responses.
- **OAuth Connect disabled:** confirm `COMPOSIO_CALLBACK_VERIFIER_ENABLED=true`,
  the HTTPS public origin, and the exact verifier URL in the Composio project.
- **Callback rejected:** return to the AverQel account that began Connect. The
  one-time callback may be expired or already used; restart authorization.
- **Connected but no tools:** inspect the MCP connection status, worker
  availability, catalog refresh event, Composio toolkit permissions, and
  session tool-execution permission.
- **Key rotation/removal:** the API disables all Composio server records,
  removes encrypted hosted-session identifiers and tool caches, and asks users
  to reconnect after the replacement key is saved.
- **Live readiness:** mocked tests verify local behavior but do not prove the
  deployment key, verifier, OAuth consent, vendor scopes, or remote tool calls.
  Run one provider-authorized read and one approval-gated side effect in a
  disposable Composio project before production enablement.

## 7. Source and tests

- `backend/app/integrations/services/composio_service.py`
- `backend/app/integrations/api/mcp.py`
- `backend/app/integrations/services/mcp_runtime.py`
- `backend/app/integrations/workers/tasks_mcp.py`
- `backend/app/deepspace/services/mcp_tool_broker.py`
- `backend/app/deepspace/services/mcp_bridge.py`
- `frontend/app/dashboard/mcp/_components/MCPComposioPanel.tsx`
- `frontend/app/dashboard/mcp/composio/callback/`
- Focused tests: `backend/tests/unit/test_composio_service.py`,
  `backend/tests/integration/test_composio_mcp.py`, and
  `frontend/tests/mcp-composio-panel.test.tsx`.

Run database-backed tests only with `./backend/scripts/test-isolated.sh` as
described in [`../../platform/03-testing.md`](../../platform/03-testing.md).
