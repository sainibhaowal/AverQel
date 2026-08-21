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

Database migration:

- `alembic/versions/20260726_0002_deepspace_agent_runtime.py`

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
