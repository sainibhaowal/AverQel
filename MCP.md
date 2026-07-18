


You are correct: having this dependency does not mean you already have a complete MCP architecture.

```text
mcp==1.27.1
```

is only the SDK library. It provides protocol communication.

Your `mcp_runtime.py` is an AverQel adapter around that SDK, but it is only a partial implementation.

Current AverQel has:

- MCP Streamable HTTP client
- Basic OAuth metadata handling
- Tool listing and tool calls
- connector mappings
- Encrypted connector credentials
- Permission and approval checks
- Audit logging
- dynamic tool exposure
- Generic server configuration
- stdio transport
- SSE fallback
- Persistent token refresh storage
- Connection registry
- Reconnect handling
- Connection status state machine
- Tool-change notifications
- Prompts catalog
- Resources catalog
- Resource templates
- Pagination and schema normalization
- General-purpose MCP server installation
- Marketplace/registry integration
- Per-server lifecycle management
- Complete MCP event persistence
- MCP Inspector-style diagnostics

That is why it feels like you only have “dependencies.” The SDK is present, but the full runtime architecture around it is incomplete.

The distinction is:

```text
SDK:
  Knows how MCP protocol messages work.

Architecture:
  Knows which servers to connect to,
  how to authenticate,
  how to persist tokens,
  how to reconnect,
  how to expose tools to the LLM,
  how to enforce permissions,
  how to audit actions,
  and how to show state in the UI.
```

OpenCode has both the SDK and a complete runtime architecture. AverQel currently has the SDK plus a partial custom runtime.

So the real task is not installing another SDK. It is completing AverQel’s MCP runtime to provide OpenCode-like lifecycle, discovery, transport, OAuth, event, and catalog behavior.



I started the Python-native implementation without deleting existing code.

Implemented:

- Generic MCP server configuration model
- Durable `mcp_servers` table
- Durable `mcp_events` table
- Encrypted `mcp_oauth_tokens` table
- Tenant-isolation RLS policies
- MCP connection status types
- Connection registry
- Lifecycle event listeners
- Catalog structure for tools, prompts, resources, and resource templates
- Tool namespacing
- JSON-schema normalization and revision tracking
- Existing SDK-backed connector behavior remains compatible

Files added:

- `backend/app/models/integrations/mcp_server.py`
- `backend/alembic/versions/20260716_0001_mcp_runtime_tables.py`

Files updated:

- `backend/app/services/integrations/mcp_runtime.py`
- `backend/app/models/__init__.py`
- `backend/app/models/integrations/__init__.py`

Verification:

- Python compilation passed.
- Model imports passed.
- Migration validation is blocked because local PostgreSQL credentials currently fail:

```text
password authentication failed for user "postgres"
```

Not complete yet:

- Real SSE and stdio sessions
- Persistent token refresh implementation
- Reconnect workers
- Tool-change subscriptions
- Prompt/resource loading
- Generic install and registry APIs
- Marketplace integration
- Inspector backend/frontend
- Full DeepSpace integration tests

This is the correct foundation, but it is not yet the complete 100% MCP platform you requested.


I implemented the next runtime capabilities now:

- Real Streamable HTTP session support
- Real SSE session support
- Real stdio process session support
- Generic transport configuration
- Command, arguments, and environment support for stdio
- Retry and exponential backoff for failed tool calls
- Prompt listing
- Resource listing
- Resource-template listing
- Connection status and catalog foundations from the previous step

The MCP runtime still compiles and the existing MCP tests pass.

The entire platform is still not 100% complete. Remaining work includes:

- Persisting refreshed OAuth tokens through encrypted database storage
- Background reconnect workers
- Server lifecycle workers
- Tool-change notification subscriptions
- Durable event repository/service
- Generic server install APIs
- MCP registry/marketplace APIs
- Inspector backend and frontend
- Frontend MCP server management UI
- Full DeepSpace/connector integration tests
- Applying the database migration; local PostgreSQL authentication is currently failing

I’m implementing this incrementally without deleting the working connector architecture.




I started the implementation, but it is **not all complete yet**.

Implemented now in `mcp_runtime.py`:

- Generic MCP server configuration
- Validation for:
  - Streamable HTTP
  - SSE
  - stdio
- Connection status state machine
- Connection registry
- Lifecycle listeners/events
- Catalog structure for:
  - tools
  - prompts
  - resources
  - resource templates
- Tool namespacing
- JSON-schema normalization
- Catalog revision tracking

Verification:

```text
mcp_runtime.py compiles successfully
MCP runtime tests pass
```

Still required before the architecture is complete:

- Actual SSE transport implementation
- Actual stdio process transport
- Persistent encrypted token refresh storage
- Automatic reconnect/backoff
- Tool-change subscriptions from connected servers
- Prompt/resource/resource-template loading
- Durable MCP event tables and repository integration
- Generic server installation API
- Official MCP registry/marketplace integration
- Per-server background lifecycle workers
- MCP Inspector-style diagnostics endpoints/UI
- Full DeepSpace and connector integration tests

I did not delete the old runtime because these remaining pieces are not implemented yet. Deleting it now would break your existing connectors.




I removed the unofficial raw registry experience and replaced it with a curated official-vendor catalog.

Now AverQel:

- Does not show `ai.smithery/...` or `co.pipeboard/...`.
- Does not allow arbitrary community package installation.
- Shows only approved vendor entries.
- Uses official vendor endpoints where verified.
- Shows official setup documentation when a vendor requires client registration.
- Requires an approved `vendor_slug` for installation.
- Rejects unknown/unverified servers.

Current official catalog includes:

- Google Gmail
- Google Drive
- Google Calendar
- Notion
- Figma
- Microsoft Learn

The public registry search endpoint has been removed from the user-facing marketplace.


Those entries (`ai.smithery/...`, `co.pipeboard/...`) were community MCP package listings—not official Google/Microsoft/Figma services. They were incorrectly being displayed as a marketplace.

I changed DeepSpace to:

- Remove public/community registry search.
- Show only curated official vendors:
  - Google Gmail
  - Google Drive
  - Google Calendar
  - Notion
  - Figma setup link
  - Microsoft Learn setup link
- Reject unknown/community IDs during installation.
- Use generic MCP OAuth discovery and signed, expiring OAuth state.
- Bind OAuth to the correct user, tenant, and server.
- Persist encrypted OAuth tokens.
- Add regression tests preventing community entries.
- Rebuild API and frontend containers successfully.

Verification passed:

- MCP runtime tests
- Official catalog tests
- Tool-contract tests
- Python compilation
- Frontend production build

Important: an official marketplace cannot automatically provide every vendor’s OAuth credentials. Vendors such as Figma or Microsoft may require their own developer registration before connection is possible.


The official-only MCP architecture is now active.

Implemented and deployed:

- Removed community registry search and entries such as Smithery/Pipeboard.
- Removed the OpenCode MCP gateway dependency.
- Added official-vendor catalog only.
- Added generic MCP OAuth discovery, signed callback state, expiry validation, tenant/user binding, and encrypted token persistence.
- Added Streamable HTTP, SSE, and stdio runtime support.
- Added token refresh persistence.
- Added pagination for tools, prompts, resources, and templates.
- Added durable MCP server/event/token tables.
- Added reconnect/lifecycle workers and list-change notifications.
- Added native MCP tool discovery into DeepSpace.
- Added generic MCP tool execution with durable events and redacted audit payloads.
- Added marketplace, OAuth, refresh, and inspector APIs.
- Added MCP marketplace and inspector frontend pages.
- Removed OpenCode-specific MCP configuration/code.
- Migration is applied: `20260716_0001`.

Verification:

- Focused MCP tests pass.
- Python compilation passes.
- Frontend production build passes.
- API, worker, scheduler, and frontend containers rebuilt successfully.
- Worker registers lifecycle MCP tasks.
- Unauthenticated catalog correctly returns `401`.

One deliberate compatibility point remains: old connector integrations are still present so existing workflows do not break. New MCP marketplace connections use the native generic architecture. Real Gmail/Notion/etc. connection testing still requires valid vendor OAuth registrations and accounts.



Further fixes completed:

- Corrected the MCP OAuth callback URL to the native server callback route.
- Added official unauthenticated Microsoft Learn MCP support.
- Verified a real live MCP handshake:
  - `https://learn.microsoft.com/api/mcp`
  - 3 tools discovered successfully.
- Added concurrent-safe durable event sequencing.
- Normalized cached tool schemas.
- Added direct Inspector links in the MCP UI.
- Updated MCP documentation.
- Applied migration `20260716_0002`.
- Rebuilt API, worker, scheduler, and frontend containers.

Focused MCP and OAuth tests pass.

The goal is not yet formally complete because legacy connector mappings still exist for backward compatibility, and the full historical DeepSpace suite still has failures from tests expecting the intentionally removed policy-planner fallback.


I made the DeepSpace agent path native-MCP-only:

- DeepSpace no longer injects legacy connector rows into its dynamic tool registry.
- Agent tools now come only from tenant-owned `MCPServer` records.
- Legacy connectors remain available only to their existing sync/API workflows, preventing accidental breakage.
- Official marketplace connections, OAuth, catalogs, permissions, lifecycle, and durable events remain active.
- Focused MCP tests pass.
- API, worker, and scheduler were rebuilt.

This is the safest way to remove hardcoded connector behavior from agent execution without destroying existing connector data and sync workflows.


The native MCP path is now the only MCP path exposed to DeepSpace agents:

- Legacy connector rows are no longer loaded into the agent’s dynamic tool registry.
- Marketplace-installed `MCPServer` records are the sole source of MCP tools.
- Legacy connector APIs remain isolated for existing sync workflows.
- Official-vendor OAuth, encrypted tokens, catalogs, lifecycle workers, approvals, and durable events remain active.

I am not marking the overall goal complete yet because the legacy connector implementation still exists for backward compatibility and the historical full test suite contains outdated expectations for removed planner fallback behavior.


Additional progress:

- Added an “Official MCP Marketplace” entry point inside the existing Connectors page.
- DeepSpace now excludes legacy connector MCP tools entirely.
- Added official GitHub MCP catalog support.
- Correctly kept Slack as “setup required” because Slack requires a registered fixed app and does not support dynamic client registration.
- Focused MCP tests pass.
- API rebuilt with the updated official catalog.

The remaining legacy connector code is isolated to its existing sync/API workflows and is no longer part of marketplace or DeepSpace agent tool discovery.


Current evidence confirms:

- Official catalog contains only:
  Google Gmail, Drive, Calendar, Notion, GitHub, Slack, Figma, Microsoft Learn.
- No unofficial registry routes or Smithery/Pipeboard entries remain.
- Migration head is `20260716_0002`.
- MCP lifecycle workers are running and scheduled.
- `/dashboard/mcp` returns HTTP 200.
- Live Microsoft MCP runtime successfully discovers 3 real tools.
- Focused MCP tests and compilation pass.

The remaining legacy connector code is isolated from marketplace and DeepSpace agent discovery; it remains only for backward-compatible connector sync APIs.


Those entries such as `ai.adramp/google-ads` and `co.pipeboard/google-ads-mcp` are registry package IDs—not Google accounts or official Google services. They represent third-party MCP server packages, and installing one could run unverified code. They do not automatically connect your Gmail/Google account.

DeepSpace is now configured to use only a curated official-vendor catalog:

- Google Gmail, Drive, Calendar
- GitHub
- Notion
- Slack and Figma setup links
- Microsoft Learn

The unverified community registry results are no longer used by the backend or marketplace UI. I rebuilt the frontend and API; reload the page without cache (`Ctrl+Shift+R`). If those old entries still appear, your browser is displaying an old cached bundle.

Verification passed:

- MCP OAuth integration tests
- MCP runtime tests
- MCP registry tests
- Python compilation
- `git diff --check`
- Database migration head: `20260716_0004`

The official catalog is only a trusted connection directory. It still requires the vendor’s own OAuth consent or setup; it cannot bypass Google, GitHub, Slack, or Figma authentication.


I found and fixed one remaining problem: the startup seed script was restoring old hardcoded connector URLs and tool lists after a restart.

Now:

- The curated official MCP catalog is authoritative.
- Legacy seed data no longer supplies MCP endpoints or tools.
- Live tools/prompts/resources are discovered from the connected official server.
- Gmail’s existing `gmail` integration is mapped to the official Google Gmail entry.
- Slack remains setup-required because Slack requires its own registered client.
- Unverified registry package IDs are not used.

The database was reseeded and verified:

- official OAuth provider metadata is present;
- hardcoded `mcp_tools` lists are empty;
- official server URLs are used;
- frontend/API/worker containers were rebuilt.

The focused MCP/OAuth test suite passes completely. If you still see entries like `ai.adramp/google-ads`, perform a hard browser refresh; those are stale frontend data from the previous registry UI.



I continued the audit and fixed two remaining issues:

- Added safe Streamable HTTP → SSE fallback during connection initialization.
- Added durable Celery reconnect retries with exponential backoff for lifecycle failures.
- Updated startup seeding so official catalog metadata remains authoritative.
- Removed stale hardcoded MCP tool lists from the database.
- Rebuilt API, worker, scheduler, and frontend containers.

Verified:

- Official-only catalog contains no community registry IDs.
- Database migration head is `20260716_0004`.
- Worker has `max_retries=100`.
- Microsoft Learn MCP live handshake succeeds.
- Focused MCP/OAuth/runtime tests pass.
- Frontend production build passes.
- `/api/v1/health/ready` returns `200`.

The full objective is not yet proven complete because real OAuth-backed Google/GitHub/Notion/Slack provider tests still require valid vendor credentials and registered applications.


Additional work completed:

- Added MCP server disconnect/uninstall API with tenant/user ownership checks.
- Added frontend “Disconnect” control that removes the stored encrypted token and server.
- Fixed OAuth scope derivation for generic MCP OAuth flows.
- Added compatibility for existing rows containing only `auth_mode: "mcp"`.
- Broader connector integration tests pass.
- MCP runtime, registry, and OAuth tests pass.
- Frontend production build passes and frontend container was rebuilt.
- Health endpoint returns `200`.

The architecture is now substantially closer to the requested official-only MCP system. Full real-vendor validation still requires actual Google/GitHub/Notion/Slack OAuth applications and credentials; those cannot be verified from this environment.



I added durable OAuth lifecycle events:

- `oauth_started`
- `oauth_completed`

These are now stored in `mcp_events` alongside catalog, connection, notification, and tool-call events.

The OAuth/runtime/registry tests still pass after the change. No real Google/GitHub/Notion/Slack credentials are configured in this deployment, so provider consent flows remain the only externally dependent verification step.


Final smoke verification passed:

- API, worker, scheduler, frontend, PostgreSQL, and Redis are running.
- Worker and scheduler register all MCP lifecycle tasks.
- Database migration head is `20260716_0004`.
- API readiness returns `200`.
- No community registry IDs or registry-search routes remain.
- Connector OAuth, connector sync, MCP runtime, and MCP registry tests all pass.
- OAuth lifecycle events are durably persisted.
- Official-only catalog behavior is enforced.

The remaining unverified boundary is real Google/GitHub/Notion/Slack consent and tool execution, because this deployment has no vendor OAuth credentials or registered client applications.


I fixed the remaining OAuth UX issue:

- After vendor consent, the callback now redirects back to `/dashboard/mcp`.
- It includes only a safe connection status and server ID.
- Signed OAuth state, tenant ownership, and callback validation remain enforced.
- API was restarted and is healthy (`200`).
- MCP/OAuth/runtime/registry tests still pass.

This means a real vendor connection now returns the user to the MCP marketplace instead of leaving the browser on a raw JSON callback response.


I removed the remaining stale hardcoded MCP endpoints and tool lists from the legacy seed source.

Now:

- The official MCP catalog is the only source of vendor endpoints.
- Startup seeding no longer contains Google/GitHub/Slack/Notion MCP URLs or tool names.
- The database was reseeded; all legacy connector `mcp_tools` arrays are empty.
- API was rebuilt and restarted.
- Health check returns `200`.
- MCP/OAuth/runtime/registry tests pass.
- `git diff --check` passes.

This prevents old connector definitions from returning after a deployment restart.


I verified the official vendor endpoints against first-party documentation and added two more official Google entries:

- Google Chat: `https://chatmcp.googleapis.com/mcp/v1`
- Google People: `https://people.googleapis.com/mcp/v1`

Google’s official documentation confirms the Gmail, Drive, Calendar, Chat, and People MCP endpoints.[Google Workspace MCP documentation](https://developers.google.com/workspace/guides/configure-mcp-servers)

I also corrected Notion to its recommended Streamable HTTP endpoint:

- `https://mcp.notion.com/mcp`

Notion documents `/sse` only as the legacy fallback.[Notion MCP documentation](https://developers.notion.com/guides/mcp/get-started-with-mcp)

Slack and Figma remain setup-required because Slack requires a registered app and Figma restricts access to supported MCP clients.[Slack MCP documentation](https://docs.slack.dev/ai/slack-mcp-server/), [Figma MCP documentation](https://developers.figma.com/docs/figma-mcp-server/)

The API was restarted, the catalog reseeded, and MCP registry/runtime tests pass.


I removed the final static MCP tool-name list from the official catalog.

Now:

- No official catalog or seed file contains hardcoded tool names.
- Legacy OAuth compatibility uses a discovery marker only.
- Native MCP runtime always discovers tools from the live server.
- Database connector metadata has zero stored hardcoded tool arrays.
- API was restarted and reseeded.
- Health returns `200`.
- MCP runtime, registry, and OAuth tests pass.

The official vendor endpoints remain based on first-party documentation, including Google Workspace and Notion’s recommended Streamable HTTP endpoint.[Google MCP documentation](https://developers.google.com/workspace/guides/configure-mcp-servers), [Notion MCP documentation](https://developers.notion.com/guides/mcp/get-started-with-mcp)


I strengthened transport behavior:

- Streamable HTTP now automatically falls back to SSE by default.
- Fallback occurs only during connection initialization.
- Tool calls are never replayed over another transport after a session starts.
- Worker, scheduler, and API were restarted with the new runtime.
- All MCP runtime/registry tests pass.
- Live Microsoft MCP discovery still succeeds with three tools.
- API readiness returns `200`.
- 

I added live MCP UI updates:

- Marketplace status refreshes every 15 seconds.
- Inspector events refresh every 5 seconds.
- Cleanup prevents timers after leaving the page.
- Frontend TypeScript/production build passes.
- Frontend container rebuilt.
- `/dashboard/mcp` returns `200`.

You can now see connection and durable-event changes without manually reloading the MCP page.



Final invariant checks are clean:

- No community registry IDs or search routes remain.
- No legacy MCP endpoints/tool lists remain in the seed source.
- Migration head: `20260716_0004`.
- API, worker, scheduler, frontend, PostgreSQL, and Redis are running.
- API health: `200`.
- Git whitespace validation passes.

The implementation is ready for your own vendor OAuth credentials; real Google/GitHub/Notion/Slack consent remains the only environment-dependent validation.


I added durable OAuth refresh auditing:

- Every encrypted token refresh now records `oauth_token_refreshed`.
- The event contains only safe metadata (`has_refresh_token`, `expires_in`), never token contents.
- API, worker, and scheduler were restarted with the change.
- Worker registers all MCP lifecycle tasks.
- MCP/OAuth/runtime/registry tests pass.
- API health returns `200`.


I improved the MCP Inspector diagnostics endpoint. It now reports:

- OAuth configured/not configured
- Tool, prompt, resource, and template counts
- Event-type counts
- Latest event
- Reconnect attempts
- Last connection error
- Full durable event history

No credentials or token values are exposed. The API was restarted, health returns `200`, and MCP tests pass.


I found and fixed a security issue in the MCP API:

- OAuth client secrets are now redacted.
- Access/refresh tokens are never returned.
- PKCE verifiers and pending OAuth state are hidden.
- Inspector and marketplace responses use the safe serializer.
- Server URLs and catalog data remain visible.
- Redaction behavior was tested directly.
- MCP tests pass and API health returns `200`.




Here is how the MCP Marketplace will work visually.

### 1. Main page: `/dashboard/mcp`

```text
┌─────────────────────────────────────────────────────────────────────┐
│ MCP Marketplace                                      [Sync Registry] │
│ Discover and connect applications through official MCP servers.     │
├─────────────────────────────────────────────────────────────────────┤
│ [Search apps, tools, vendors...]                                    │
│                                                                     │
│ Categories: [All] [Productivity] [Development] [Communication]      │
│            [Files] [Knowledge] [Finance] [Marketing]               │
│                                                                     │
│ View: [Marketplace] [Installed]                                     │
│ Filters: [Official] [Verified] [Remote] [Local]                    │
├─────────────────────────────────────────────────────────────────────┤
│  Google Drive       OFFICIAL ✓     Remote · OAuth                   │
│  Search and manage files                                             │
│  [View details]                                      [Connect]       │
├─────────────────────────────────────────────────────────────────────┤
│  GitHub              OFFICIAL ✓     Remote · OAuth                   │
│  Repositories, issues, pull requests                                 │
│  [View details]                                      [Connect]       │
├─────────────────────────────────────────────────────────────────────┤
│  Notion              OFFICIAL ✓     Remote · OAuth                   │
│  Search and read workspace pages                                     │
│  [View details]                                      [Connect]       │
└─────────────────────────────────────────────────────────────────────┘
```

Each marketplace card will show:

- App/vendor name
- Logo
- Description
- Official badge
- Verified badge
- Remote or local transport
- OAuth or setup requirement
- Number of discovered tools
- Last registry update
- `Connect`, `Install`, or `Setup required`

### 2. Installed tab

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Installed MCP Servers                                                │
├─────────────────────────────────────────────────────────────────────┤
│ Google Drive        CONNECTED                                       │
│ Remote · OAuth · 18 tools                                           │
│ Last catalog sync: 2 minutes ago                                    │
│ [Refresh catalog] [Inspect tools] [Disconnect]                      │
├─────────────────────────────────────────────────────────────────────┤
│ Microsoft Learn     CONNECTED                                       │
│ Remote · Anonymous · 12 tools                                       │
│ Last catalog sync: 5 minutes ago                                    │
│ [Refresh catalog] [Inspect tools] [Disconnect]                      │
└─────────────────────────────────────────────────────────────────────┘
```

Status colors:

- Green: Connected
- Yellow: Needs authentication
- Blue: Syncing
- Red: Failed
- Gray: Disconnected

### 3. App details page/modal

When the user clicks `View details`:

```text
┌─────────────────────────────────────────────────────┐
│ Google Drive                              OFFICIAL ✓ │
│                                                     │
│ Official Google Workspace Drive MCP server.         │
│                                                     │
│ Publisher: Google                                   │
│ Transport: Streamable HTTP                          │
│ Authentication: OAuth 2.0                           │
│ Endpoint: drivemcp.googleapis.com/mcp/v1            │
│                                                     │
│ Discovered capabilities                             │
│ • search_files                                      │
│ • get_file                                          │
│ • download_file                                     │
│ • list_folders                                      │
│                                                     │
│ Source: Official MCP Registry                       │
│ Last verified: July 17, 2026                        │
│                                                     │
│                         [Connect Google Drive]      │
└─────────────────────────────────────────────────────┘
```

### 4. OAuth connection flow

```text
User clicks Connect
        │
        ▼
Create MCP server record
        │
        ▼
Show "Connect Google account"
        │
        ▼
Redirect to Google OAuth
        │
        ▼
User grants permission
        │
        ▼
Callback returns to AverQel
        │
        ▼
Encrypt and store OAuth token
        │
        ▼
Start catalog refresh
        │
        ▼
Discover tools, prompts, and resources
        │
        ▼
Show server as CONNECTED
```

For an anonymous server such as Microsoft Learn:

```text
User clicks Connect
        │
        ▼
Install server
        │
        ▼
Immediately refresh catalog
        │
        ▼
Show CONNECTED
```

For a local `stdio` server:

```text
User clicks Install
        │
        ▼
Show required package and command
        │
        ▼
User confirms local setup
        │
        ▼
AverQel starts the configured process
        │
        ▼
Discover local tools
```

### 5. Registry synchronization

The backend periodically calls the official MCP Registry:

```text
Official MCP Registry
        │
        ▼
Registry sync worker
        │
        ▼
Normalize server metadata
        │
        ▼
Save/update database records
        │
        ▼
Marketplace API
        │
        ▼
MCP Marketplace UI
```

The marketplace will distinguish clearly between:

- `Official` — publisher is verified as the actual company
- `Verified` — metadata/endpoint passed validation
- `Community` — publicly listed but not vendor-confirmed
- `Setup required` — no direct endpoint or vendor registration is needed
- `Connect` — AverQel can start OAuth or install directly

This gives users one page to discover everything, while keeping installed connections, authentication, catalog refresh, and tool inspection separate and understandable.


No—not everything in that specification is complete yet.

Implemented:

- Registry database storage
- Registry sync service
- Marketplace API
- Search and pagination
- Official/verified metadata
- Marketplace and Installed tabs
- Basic connect/setup actions
- Registry sync button
- Installed server status and refresh

Still missing or incomplete:

- Category filter UI
- Official/verified/remote/local filter controls
- App details modal/page
- Logos
- Discovered tool count on marketplace cards
- Last catalog-sync timestamp in the UI
- Full status color styling
- Inspect and disconnect buttons in the new Installed view
- Automatic scheduled registry synchronization
- Reliable mapping from registry entries to official vendor slugs
- Local `stdio` package installation flow
- Community/custom MCP endpoint installation
- Complete OAuth setup UI for vendors requiring registration
- Marketplace tests and live MCP integration tests

So the current version is a working foundation, not the complete final marketplace described in your specification.

Logo storage/rendering
Tool count and last catalog-sync timestamp in marketplace cards
Arbitrary community remote-server installation
Local stdio package execution/install UX
Vendor-registration-specific OAuth screens
Live end-to-end tests against real MCP servers


Add logo URL, tool count, and last-sync fields to the registry model and migration.
Add a safe custom remote-server installation endpoint.
Add vendor-specific OAuth metadata and setup screens.
Add a controlled local stdio runner with command allowlisting, sandboxing, timeouts, and environment isolation.
Add real MCP integration tests using mock servers plus at least one live remote server.
Add security checks for registry metadata and remote endpoints.


No. The integration is not 100% complete yet.

Covered:

- MCP SDK runtime
- HTTP, SSE, and stdio transport support
- OAuth token encryption and refresh persistence
- MCP server database models
- Server install/list/refresh/delete APIs
- Official vendor catalog
- Registry import and marketplace database
- Marketplace search, pagination, transport and verified filters
- Marketplace/Installed UI tabs
- Details modal
- Connect/setup actions
- Catalog refresh and lifecycle workers
- Dynamic tool discovery and execution
- Inspector and event auditing
- Scheduled registry synchronization
- Backend compilation
- Frontend TypeScript validation

Still incomplete:

- Logo metadata/storage/rendering
- Tool count and last catalog-sync fields in marketplace cards
- Safe arbitrary remote MCP installation with SSRF protection
- Full community-server installation flow
- Sandboxed/allowlisted local stdio execution
- Vendor-specific OAuth registration screens
- Complete category filtering and category normalization
- Reliable registry-to-official-vendor mapping
- Security validation of registry endpoints/packages
- Live remote MCP integration tests
- Full marketplace/API/frontend automated tests
- Database migration execution in the deployed environment

Also, `pytest` was unavailable in the environment, so the test suite has not been run. The migration must still be applied:

```bash
cd /home/ravi/Projects/AverQel/backend
alembic upgrade head
```

Therefore the accurate status is: strong functional foundation, but not yet a 100% production-verified MCP marketplace.

I can implement the repository-side code, but I cannot complete the full request as a verified end-to-end deployment from this workspace.

There are two hard blockers:

1. The worktree already contains extensive unrelated modifications across the backend, frontend, migrations, CI, and desktop application. A large cross-cutting patch risks overwriting user work.

2. Several requested items cannot be completed or verified without deployment-specific decisions and access:

   - Running migrations against the deployed database
   - Live MCP endpoints and OAuth credentials
   - Vendor client-registration details
   - Docker/Kubernetes sandbox configuration for stdio
   - Production egress and SSRF policy
   - Approved package/signature trust rules

The code currently has the marketplace foundation, but claiming all requested features are complete would be false. The remaining work must be handled in a controlled branch with:

- a declared sandbox architecture,
- a remote-server trust policy,
- test MCP endpoints/credentials,
- deployment database access,
- and protection for the existing uncommitted changes.

Without those inputs, I can continue adding local code, but I cannot honestly deliver “100% end-to-end, nothing left.”







The remaining problems are not all the same. They fall into four groups.

### 1. Marketplace data is incomplete

Problem:

- Registry entries do not consistently contain logos, categories, tool counts, or sync timestamps.
- Official vendor matching is currently based mainly on URL/name heuristics.
- Registry metadata is not fully normalized.

Fix:

- Add fields such as `logo_url`, `tool_count`, `last_catalog_sync`, `normalized_categories`, and `verification_reason`.
- Normalize categories during registry sync.
- Maintain an explicit official-vendor mapping table using stable registry IDs and verified domains.
- Update tool counts and sync timestamps whenever catalog refresh succeeds.
- Render these fields on marketplace cards and the details modal.

### 2. Remote server installation is unsafe if unrestricted

Problem:

Allowing any user or registry entry to submit an arbitrary URL can create SSRF attacks. The backend could be tricked into connecting to:

- `localhost`
- private IPs
- cloud metadata services
- internal admin endpoints
- malicious redirect targets

Fix:

- Require HTTPS except explicitly approved development environments.
- Resolve DNS before connecting.
- Reject loopback, private, link-local, multicast, and metadata IP ranges.
- Re-check every redirect target.
- Enforce connection and response-size limits.
- Store the normalized URL and an audit event.
- Separate “registry-listed,” “verified,” and “user-provided” servers.

### 3. Local stdio servers can execute arbitrary code

Problem:

An MCP stdio server is a process. If the application runs a registry-provided command directly, that command can read secrets, modify files, or compromise the host.

Fix:

- Never run arbitrary commands in the API process.
- Use a separate worker or sandbox container.
- Allow only approved runtimes and packages.
- Run as a non-root user.
- Provide an isolated filesystem and environment.
- Block host-network access unless explicitly allowed.
- Enforce CPU, memory, process, timeout, and output limits.
- Record the exact package/version/hash before execution.
- Require administrator approval for new commands.

Until this exists, stdio entries should remain “Setup required.”

### 4. OAuth and production verification are environment-dependent

Problem:

OAuth is not generic. Google, GitHub, Slack, Figma, Notion, and Microsoft can require different:

- client IDs
- redirect URLs
- scopes
- registration methods
- consent screens
- token formats

Also, live integration tests require real reachable servers and credentials.

Fix:

- Store OAuth provider metadata per vendor.
- Add vendor-specific setup states in the UI.
- Validate redirect URI and scopes before starting OAuth.
- Use mock MCP servers for repeatable automated tests.
- Add optional live tests using dedicated test credentials.
- Run migrations and smoke tests in staging before production.

### What I would fix first

1. Database fields and migration for logo/tool count/sync metadata.
2. Registry normalization and official-vendor mapping.
3. SSRF-protected custom remote-server API.
4. Marketplace details and connection states.
5. Mock MCP integration test server.
6. Sandboxed stdio worker.
7. Vendor-specific OAuth setup.
8. Staging migration and live smoke tests.

The core issue is that the current implementation can discover and connect to curated MCP servers, but it does not yet have the trust, isolation, and verification layers required to safely support every public MCP server.


I’ve started the implementation as a staged task and preserved the existing worktree.

The implementation order is now:

1. Audit and protect existing MCP changes.
2. Add registry metadata, normalization, verification, logos, tool counts, and sync timestamps.
3. Add SSRF-protected custom remote installation.
4. Add Docker-isolated stdio execution configuration.
5. Add vendor-specific OAuth setup states.
6. Complete marketplace UI details and filters.
7. Add mock MCP integration tests.
8. Document and prepare staging-only migration/live-test execution.

I’m using Docker isolation as the default stdio design and treating deployment migration/live-server tests as staging actions rather than pretending they can be verified locally.

SSRF-protected custom remote installation
Community-server installation flow
Docker-isolated stdio runner
Vendor-specific OAuth registration screens
Registry endpoint/package security validation
Tool-count and sync timestamp updates from catalog refresh
Marketplace rendering for logos/counts/timestamps
Mock and live integration tests
Running the migration against staging/production


SSRF-protected custom remote installation
Community-server installation flow
Docker-isolated stdio runner
Vendor-specific OAuth registration screens
Registry endpoint/package security validation
Tool-count and sync timestamp updates from catalog refresh
Marketplace rendering for logos/counts/timestamps
Mock and live integration tests
Running the migration against staging/production