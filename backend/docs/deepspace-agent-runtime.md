# DeepSpace runtime agent loop

DeepSpace is a productivity runtime, not an IDE or operating-system agent. Its
loop continues dynamically until the model calls `final` after verification,
the user cancels, the client disconnects, a required user answer is requested,
or a runtime safety policy reports a blocker.

## Runtime contract

The loop is owned by `app/deepspace/services/chat_service.py`. There is no
fixed 12-round limit. Each model turn can emit multiple tool calls. Independent
read-only calls run concurrently; note writes, task writes, questions, and
final verification are serialized to protect state.

Native provider events are forwarded as DeepSpace SSE events, including
`thinking`, `delta`, `tool_delta`, `tool_start`, `tool_result`, `tool_error`,
`observing`, `ask_user_question`, and `agent_status`.

Model narration emitted before a tool call or `ask_user` pause is persisted as
an ordered activity step. A paused, resumed, cancelled, or reloaded turn keeps
that narration beside the tool and question events instead of rebuilding the
turn from only its final answer.

## Productivity tools

The DeepSpace allowlist contains:

- task planning and verification: `todo_write`, `todo_read`, `todo_check`,
  `todo_mark`
- active-note work: `read`, `write`
- state and reasoning: `observe`, `analyze`, `final`
- current web work: `web_search`, `url_read`, `image_read`
- required clarification: `ask_user`

`read` and `write` are limited to the active DeepSpace note in the application
database. URL and image tools use server-side HTTP with timeouts, redirect
limits, DNS/IP private-network blocking, domain allowlists, response-size
limits, and provider/user rate limiting. The model never receives shell,
terminal, arbitrary cURL, filesystem, or file-explorer access.

## MCP-connected productivity tools

MCP is an optional, conversation-scoped extension of the DeepSpace tool
registry. It does not replace or bypass the existing MCP integration. A tool
is exposed to DeepSpace only when all of the following are true:

- the MCP server belongs to the authenticated tenant and user;
- the server is enabled, connected, backed by an approved provider, and has a
  fresh discovered catalog;
- the server policy is enabled and explicitly attached to the current
  conversation.

The bridge is implemented in
`app/deepspace/services/mcp_bridge.py`. It namespaces model-facing tool names,
uses the existing MCP catalog and policy evaluator, and forwards execution to
`app/integrations/services/mcp_runtime.py`. OAuth, encrypted credentials,
transport, provider checks, catalog refresh, and tenant ownership remain owned
by the MCP integration service.

### Deferred MCP tool loading

DeepSpace does not send a connected server's complete tool catalogue or input
schemas to the model. `app/deepspace/services/mcp_tool_broker.py` keeps the
conversation-scoped bindings private and exposes only three small broker
functions:

- `mcp_search_tools` returns a bounded list of matching tool references;
- `mcp_get_tool_schema` returns one compact schema for one selected reference;
- `mcp_call_tool` resolves the reference back to the already authorized bridge
  binding and executes that exact tool.

This is universal for every connected MCP server. It does not depend on a
Notion-, Gmail-, Slack-, or provider-specific tool list. New servers are
searchable from their discovered names, descriptions, and parameter names as
soon as their normal catalog refresh succeeds. The model never receives the
full catalogue, raw server configuration, credentials, or transport details.

The backend still uses the original exact catalog for execution validation.
Before every remote call, the existing tenant/user ownership lookup,
connection status, catalog revision, policy, risk classification, approval
gate, audit event, and MCP transport path run unchanged. Successful model
output is bounded by `DEEPSPACE_MCP_MAX_RESULT_CHARS` so a large remote page
cannot refill the conversation context unexpectedly.

The runtime settings are:

- `DEEPSPACE_MCP_MAX_SEARCH_RESULTS=5`;
- `DEEPSPACE_MCP_MAX_SCHEMA_CHARS=6000`;
- `DEEPSPACE_MCP_MAX_RESULT_CHARS=12000`.
- `DEEPSPACE_MCP_MAX_CALLS_PER_TURN=8`;
- `DEEPSPACE_MCP_MAX_DISCOVERY_CALLS_PER_TURN=8`;
- `DEEPSPACE_MCP_MAX_RESULT_CHARS_PER_TURN=60000`.
- `DEEPSPACE_MCP_MAX_ARGUMENT_CHARS_PER_CALL=20000`.

Deferred loading is mandatory. There is no direct-schema fallback path, so a
large MCP catalogue cannot silently re-enter model context after deployment.
No MCP connection or approval route changes are required for rollout.

Read-only MCP actions can run automatically when the configured policy allows
them. Writes, deletes, sends, and other external side effects pause the
DeepSpace run and emit a visible approval request. The UI resolves the request
through `POST /api/v1/deepspace/chats/{conversation_id}/approvals/{approval_id}`;
an approved request resumes the same persisted run, while a denial blocks it.
Approval decisions are server-side, tenant-scoped, persisted in the run
checkpoint, and cannot be replayed after resolution.

To attach a server, use the existing MCP conversation-scope endpoints:
`GET /api/v1/mcp/conversations/{conversation_id}/connections` and
`PUT /api/v1/mcp/conversations/{conversation_id}/connections/{server_id}`.
The DeepSpace stream then discovers the attached tools automatically. No MCP
tool gets shell, filesystem, terminal, arbitrary cURL, or operating-system
access through this bridge.

## Durability and safety

### Current-turn memory boundary

Persisted conversation history and approved durable memory are reference
context, not executable instructions. The latest user message is authoritative
for the current turn. DeepSpace does not reuse historical MCP arguments,
repository names, file names, account identities, approvals, or task IDs
unless the user repeats them in the current request or a fresh read-only
lookup verifies them. Previous failures may guide recovery, but are not treated
as current facts. An unfinished task ledger is resumed only by an explicit or
clearly matching continuation; unrelated requests cannot read or modify that
old task state or be blocked by it.

`DeepSpaceRuntimeStore` persists each run in `deepspace_agent_runs` and retains
up to 10,000 bounded step records per run in `deepspace_agent_steps`. Retained
steps are audit/checkpoint data and are not blindly injected into the model
context. The runtime has maximum-runtime, concurrent read-tool, and URL-size
policies, plus duplicate-call detection, retries, cancellation, tenant/user
scoping, and persisted task dependencies.

The existing `POST /api/v1/deepspace/chats/{conversation_id}/cancel` route now
sets the durable cancellation flag. The stream checks it between model and
tool steps, so a separate request can stop a long run safely.

### Durable composer queue

An active DeepSpace response never disables the composer. A normal additional
message is persisted in `deepspace_queued_turns` and dispatched in FIFO order
after the active turn reaches a terminal state. **Steer** persists the new
message at priority and asks the active run to cancel; it does not depend on a
browser tab remaining open. Each record stores the submitting tenant, user,
conversation, request id, and an authorization snapshot. Queue reads, removal,
and dispatch are all scoped to that same tenant/user/conversation boundary.

The queue API is:

- `GET /api/v1/deepspace/chats/{conversation_id}/queue`
- `POST /api/v1/deepspace/chats/{conversation_id}/queue`
- `POST /api/v1/deepspace/chats/queued/{client_request_id}/cancel`

The initial normal stream is also first persisted as a queue turn. A browser
refresh reconnects to the durable event stream, while the queue continues in
the worker. Approval and clarification resumes deliberately reuse the original
request id, preserving their queue slot rather than leaving a paused turn that
could block later messages.

Database migrations include:

- `alembic/versions/20260726_0002_deepspace_agent_runtime.py`
- `alembic/versions/20260916_0001_deepspace_queued_turns.py`
- `alembic/versions/20260916_0002_deepspace_request_metrics.py`
- `alembic/versions/20260917_0001_cascade_deepspace_runtime_and_snapshots.py`
- `alembic/versions/20260918_0001_deepspace_context_summaries.py`

The queue, metrics, cascade, and context-summary changes are present in the
current worktree and require migration, regression, and load validation before
production rollout.

This runtime does not modify Query, terminal, file-explorer, connector, or
operating-system storage behavior. It adds only the DeepSpace adapter and the
approval/resume path described above; the existing MCP transport and security
boundary remain unchanged.

### OAuth continuity

MCP OAuth tokens are stored encrypted in `mcp_oauth_tokens`. Each worker
restores the persisted expiry before opening a session, so the MCP SDK can
refresh an expired access token with the stored refresh token before the first
request. Refreshed access tokens are encrypted and persisted again without
replacing a refresh token when a provider omits it from the refresh response.

Read-only tool calls may make a bounded reconnect attempt after a transient
session/auth failure. Writes, deletes, and outbound messages are never retried
automatically because a remote service may already have applied their side
effect. Remote failures are returned with a stable category and a safe
recovery message; token values and provider response bodies are not exposed.

If a provider revokes a grant, changes scopes, or disables an account, no
client can silently repair that authorization. In that case the connection is
reported as requiring reconnection, while other MCP connections and the chat
run remain isolated.

The external provider account does not need to use the same email address as
the AverQel login. OAuth is started by the authenticated AverQel user, but the
Google or GitHub account selected in the consent screen is stored as that
user's encrypted MCP connection. Tenant and user ownership are still checked
on every discovery and tool call; a different provider email never grants
cross-user access.

SSE transport uses the installed MCP SDK's client-factory contract and the
same SSRF-safe HTTP client as Streamable HTTP. Provider tool errors are
returned as redacted actionable diagnostics, while access tokens and raw
credentials remain excluded from events and responses.

For Google Workspace connections, the Google product API and its matching MCP
API must both be enabled in the Google Cloud project. For Gmail these are
`gmail.googleapis.com` and `gmailmcp.googleapis.com`. A successful Gmail API
profile check does not prove that the Gmail MCP API is enabled; the remote MCP
server can still return `The caller does not have permission` until that
service is enabled and the OAuth consent configuration is saved.
