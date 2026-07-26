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
