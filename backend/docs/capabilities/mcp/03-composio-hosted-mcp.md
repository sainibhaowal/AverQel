# Composio hosted MCP apps

**Status:** implemented locally; live OAuth and tool execution still require a user-owned Composio project key and provider smoke testing.

This guide describes the Composio app catalog in Dashboard → MCP Marketplace and the **MCP** section under Providers. The marketplace uses Composio's live toolkit catalog. It no longer lists AverQel's eight bundled Google, GitHub, Notion, and Slack connector cards. Existing installed connections are retained; this change does not delete their records or revoke their provider accounts.

Composio's catalog is dynamic. AverQel fetches and paginates toolkit and tool metadata from the Composio API. The count shown is the count reported by that API at request time; it can change, so documentation does not promise a fixed number of apps. Composio catalog entries are not represented as individually reviewed AverQel providers. Cards load app icons from Composio's maintained logo CDN using each validated toolkit slug. This avoids stale app-owned image URLs in toolkit metadata. If a CDN image is missing or fails to load, the card uses a neutral local fallback. On wide screens, the responsive catalog displays up to five cards per row.

## 1. User setup

1. Create or select your own Composio project and copy its project API key.
2. In AverQel, open **Providers → MCP**, choose **+** to browse provider families, then select **Composio**. Enter the key in its setup panel and choose **Validate and save**. AverQel validates catalog access before storing it.
3. Open **MCP Marketplace**, search or browse the live catalog, and choose **View details** to inspect the description, app/authentication links, categories, authentication methods, catalog version, and available tools with their descriptions and input fields. Tool results load in pages; choose **Load more tools** when shown.
4. Choose **Connect**. For an OAuth app, complete that app's consent flow in Composio. Each app authorization is associated with your AverQel account; each user must authorize their own external app account.
5. After connection, the MCP worker discovers the app's tools. Use DeepSpace to call them under the same MCP policy and approval flow as other connections.

A Composio project key is a secret. AverQel encrypts it with the configured connector-secret backend and binds the encryption associated data to the tenant and user IDs. The database row is keyed by tenant and user and has row-level security requiring both IDs. Credential reads, replacement, and removal are performed in the authenticated user's scope. The key is never returned to the browser. The running AverQel server decrypts it when making Composio requests, so this is not end-to-end encryption from the server.

This per-user setup gives each person control over the Composio project and
external accounts used by their tools, and prevents another AverQel account
from using the same stored credential or claiming the resulting sessions. The
encryption protects the credential while stored; it does not hide requests or
results from AverQel's running backend, Composio, or the connected app provider.

Replacing a key disables and clears hosted sessions belonging to that same AverQel account, which must then reconnect. Removing a key deletes only that user's stored key and disables only that user's Composio sessions. Deleting the AverQel account cascades to its credential row. No user can use another user's Composio key through AverQel.

## 2. OAuth redirect and identity verification

The server operator must configure the existing connector-secret encryption backend and retain active/previous key IDs according to the secret-rotation policy. Do not put user project keys into source control or a shared server environment variable.

OAuth apps require `AVERQEL_PUBLIC_ORIGIN` to contain the canonical public HTTPS origin. Local development may use an HTTP localhost origin. Users do not configure a shared AverQel Composio key or register a callback verifier in their Composio project. Once a key is saved, the Marketplace starts the OAuth flow and returns the user to AverQel.

The browser callback includes Composio's status and connected-account ID. These query values are untrusted. Before enabling the app, AverQel requires all of the following:

- the callback is authenticated as the same AverQel account that started the connection;
- the connected-account ID exactly matches the pending request saved on that account's app row;
- Composio reports that the pending account is active and belongs to the requested toolkit;
- if Composio returns its external user ID, it matches the tenant/user-derived identity used to create the request.

The pending request is single-use in AverQel: success clears it, and replay or a callback from another account is rejected. OAuth still requires a working public callback URL. Composio toolkits marked as requiring no account authorization can be added without OAuth. See [Composio's callback and connected-account guidance](https://docs.composio.dev/docs/authentication/manually-authenticating) and [Python ConnectedAccounts reference](https://docs.composio.dev/reference/sdk-reference/python/connected-accounts).

## 3. API and data ownership

| Interface or data | Purpose and boundary |
| --- | --- |
| `GET /api/v1/mcp/composio/status` | Reports whether the signed-in user's key exists and whether an OAuth callback origin is available. It never returns the key. |
| `PUT /api/v1/mcp/composio/credential` | Validates and stores the signed-in user's encrypted key. Requires normal authenticated access, not platform-admin access. |
| `DELETE /api/v1/mcp/composio/credential` | Removes only the signed-in user's key and invalidates that user's Composio sessions. |
| `GET /api/v1/mcp/composio/toolkits` and `/toolkits/{slug}` | Fetch paginated live app metadata (logo, app/auth-guide URLs, categories, authentication methods and catalog version/timestamps) and tool descriptions/input schemas using the authenticated user's key. The API does not provide a per-app author or separate public MCP endpoint for every toolkit. |
| `POST /api/v1/mcp/composio/toolkits/{slug}/connect` and `/oauth/complete` | Starts or completes a user-owned Composio hosted session. |
| `composio_credentials` | Composite tenant/user key; encrypted ciphertext, nonce, key ID, and owner-only row-level security. |
| `composio_legacy_platform_credentials` | Created only when upgrading an installation with the former platform-wide singleton key table. Preserves that encrypted record under its prior platform-admin-only policy; the user-owned Composio integration does not read or assign it to any account. |
| `mcp_servers` Composio rows | One server record per tenant, user, and toolkit. The hosted session ID is encrypted with tenant, user, and server IDs as associated data. |

The former `/api/v1/admin/providers/composio` routes are removed. An administrator does not configure a shared key for users.

Composio toolkit slugs are opaque identifiers and must be preserved exactly, including a leading underscore where present (for example, `_1password`). AverQel uses the same slug for details, connection, tool discovery, and the Composio logo CDN.

## 4. DeepSpace tools and approvals

Composio tools run through the existing MCP runtime and DeepSpace broker. The broker checks the connection owner, tool catalog, policy, and action risk before execution. Reads can run according to the user's saved policy. Writes, deletions, and external messages require an explicit approval card; changing a tool's normal mode cannot bypass the side-effect approval check. The model receives bounded tool references rather than the complete app catalog or any credential.

A successful Composio catalog response does not guarantee that every app has OAuth, is enabled for every Composio project, or will accept a requested action. Users must review the requested scopes and the tool's approval card before authorizing or approving an action.

## 5. Data handling and privacy

AverQel uses the project key from the currently authenticated user to call Composio. The key remains encrypted in the database but is readable by the running backend during those calls. Composio processes authorization and tool requests; the connected app provider processes the resulting actions and data. This is not end-to-end encryption from AverQel's server, Composio, or the connected provider.

The integration stores an encrypted Composio hosted-session identifier in AverQel and does not store the provider password or provider OAuth token in the local MCP credential table. Disconnecting an app removes its local session data; users should also revoke access in Composio or the connected provider when they want the remote authorization removed. Do not claim that AverQel has deleted data held by Composio or a connected provider.

## 6. Troubleshooting

- **Marketplace asks for a key:** open **Providers → MCP** and add your own Composio project API key. No platform-admin allowlist or admin key setup is required.
- **Composio status returns HTTP 500:** check the API log and database migration head. Revision `20261019_0004` repairs databases where the old platform-only credential table was recorded as the account-scoped migration. It preserves the old table and creates the per-user table; do not delete or manually reshape the credential table.
- **Key validation fails:** confirm the key belongs to your Composio project, has catalog/session permissions, and that outbound HTTPS/DNS is available. Provider exception details are redacted from the response.
- **OAuth Connect is disabled:** configure the deployment's public HTTPS origin (`AVERQEL_PUBLIC_ORIGIN`). Local development can use an HTTP localhost origin. No Composio project callback-verifier setup is required.
- **Callback is rejected:** return to the AverQel account that started authorization and restart the app connection. AverQel accepts only the pending Composio account ID saved for that user's selected app.
- **Connected app has no tools:** inspect its Installed connection status, then refresh its catalog. Check worker health and the Composio project's session/tool permissions.
- **Key replaced or removed:** only that account's Composio sessions are disabled. Reconnect its apps after a replacement key is saved.
- **Live readiness:** isolated tests verify application behavior, not a real Composio key, vendor consent screen, public callback route, or remote action. Perform a live test with a disposable Composio project before enabling use for customers.
