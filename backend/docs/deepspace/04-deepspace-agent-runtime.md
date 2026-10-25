# 04. DeepSpace runtime agent loop

DeepSpace is a productivity runtime, not an IDE or operating-system agent. It
answers directly when no action is needed. When work requires tools, it loads
only selected schemas from the request-authorized catalog. Substantial
multi-step work can use a persisted task plan; after the plan is verified, the
model responds in ordinary assistant text. Cancellation, user input, approval,
the durable run deadline, or a runtime safety blocker can pause execution.

## Runtime contract

The loop is owned by `app/deepspace/services/chat_service.py`. Provider calls
continue within the durable run deadline and existing per-capability budgets.
Independent native read-only calls can run concurrently during an in-progress
task when their inputs do not depend on one another. The same provider turn
cannot combine that batch with discovery, MCP, task-ledger changes, writes,
questions, approvals, or verification. Those operations are ordered to protect
state. Native schemas use
the compact catalog and exact schema-loading flow described in
`03-deepspace-agent-loop.md`; MCP uses its separate live broker.

Native provider events are forwarded as DeepSpace SSE events, including
`thinking`, `delta`, `tool_delta`, `tool_start`, `tool_result`, `tool_error`,
`ask_user_question`, and `agent_status`. These events describe actual provider
output or runtime actions; DeepSpace does not synthesize an extra user prompt
to advance its task loop.

Completed reply metrics separate two first-output measurements. End-to-end
TTFT runs from DeepSpace beginning to handle the request to the first visible
answer text, so it includes routing, context preparation, provider wait, and
reasoning or tool work before the answer. Provider first-output time runs from
the first provider/connector request to the first output event received by the
server. It includes network and connector overhead and, for Codex Desktop, the
local desktop relay; it is not the model vendor's internal compute latency.

Output tokens per second uses the provider's exact completion-token usage over
the summed interval between the first and last output events received in each
generation round. Provider completion-token counts may include hidden
reasoning or tool-call tokens; the metric never exposes their content. Speed
is explicitly unavailable if exact usage is missing for any output round, a
provider only returns a single output event, the stream is buffered, or the
measured interval is too short. It is not estimated from visible text. Chat
Completions requests ask for `stream_options.include_usage` for providers with
documented support (OpenAI, DeepSeek, NVIDIA NIM, Mistral, OpenRouter, LM
Studio, and vLLM); older endpoints that explicitly reject this optional field
are retried once without it. Other providers still contribute usage if they
return it natively. A custom OpenAI-compatible endpoint can opt in through
`metadata_json.openai_compatible.stream_usage: "enabled"` after confirming
that endpoint supports the standard field. Responses API providers, including
Codex, use their native completion usage event. Estimated local context tokens
and provider-reported usage remain separate values. The measurements and any
unavailable reason are stored in assistant message metadata so chat history
can restore them without a schema migration.

### OpenAI Codex Desktop provider

The OpenAI provider can use an API key or the desktop-only `codex_desktop`
authentication mode. In Electron, users can reuse a local Codex CLI ChatGPT
login or sign in through OpenAI in the system browser. The CLI path uses the
Codex app-server's native provider route under AverQel's restricted permission
profile; it does not read the CLI credential file or copy its tokens. The
browser path validates the OpenAI identity token and encrypts account tokens
with Electron `safeStorage` in the user's desktop profile. The backend receives
only the opaque account ID and selected account model catalog; OAuth tokens
remain on the desktop.

DeepSpace dispatches this mode to `OpenAICodexProvider`, which sends a bounded
inference request to the Electron runtime over the authenticated
`/deepspace/codex-runtime/ws` relay. The browser OAuth path uses the Responses
API; the local CLI path uses Codex app-server with the selected model and
reasoning effort. A short-lived one-use ticket authenticates
the WebSocket; the account owner and `queries:run` permission are checked
before the runtime is registered. Redis carries transient request/response
frames between API workers and that user's desktop connection. The desktop
streams the OpenAI response back to DeepSpace, and cancellation is relayed to
the local request. If the desktop disconnects, the turn fails with a runtime
unavailable error; this mode does not perform an automatic API-key fallback.
Before a local CLI turn starts, OpenAI-compatible function definitions are
coalesced into a single AverQel namespace and duplicate names are removed. This
matches the Codex app-server contract and prevents a valid DeepSpace tool set
from being rejected before model execution.
Queued relay requests are discarded when runtime ownership ends, so an old
prompt cannot start later after the desktop reconnects.

The Responses request sets `store: false` and streams output. Both paths support
the DeepSpace text, attached-image, and function-tool inputs; the integration
does not expose embeddings or arbitrary OpenAI hosted tools. For local CLI
accounts, DeepSpace reads each model's advertised effort list and preserves the
model's native value when sending the request. This includes Codex `minimal` and
`ultra`, the existing Low, Medium, High, Very High, and Extreme High choices,
and other safe values advertised by a model. Only values listed for the selected
model are selectable. The browser account's `/models` catalog may omit
per-model effort metadata; DeepSpace uses that metadata when present and
otherwise retains the existing OpenAI reasoning profile. It does not claim
that the browser account's profile is an exact account-specific capability list.
OpenAI model availability, plan eligibility, and supported reasoning levels
remain account- and model-dependent. The Electron bridge keeps OAuth tokens off
the server, but DeepSpace prompts and
conversation history still pass through and are stored by the existing AverQel
backend retention path. ChatGPT plan usage-limit errors are surfaced with
OpenAI's error code and request ID where available. Those quota failures are
not retried automatically and do not trip the provider circuit breaker; the
user can retry after OpenAI allows another request.

For other providers, the DeepSpace Think menu uses verified model profiles or
effort levels advertised by the provider's model catalog. The selected model's
cached descriptor is rendered first; if its capability metadata is missing or
stale, the browser refreshes that provider's catalog asynchronously and merges
the refreshed descriptor into the model list. LM Studio's `/api/v1/models`
reasoning options are used when the server returns them, and the selected
option is sent using its native value. Ollama discovery reads each installed
model's `/api/show` thinking descriptor. Named values are shown as model
options; boolean-only descriptors show On/Off, and `[false]` shows no thinking
control. Ollama discovery uses bounded parallel requests; a missing or
unsupported `/api/show` response leaves that model on its provider default.

NVIDIA NIM Nemotron 3 Ultra supports Off, Medium, and High; Nemotron 3 Super
supports Off, Low, and High. These choices are translated to the model's
documented `reasoning_effort` request values. Nemotron 3 Nano exposes an On/Off
thinking toggle without effort levels. Existing cache rows and the active chat
assignment are overlaid with verified profiles in provider model responses, so
a known assigned model works before its first catalog cache entry and no
migration or manual cache reset is needed. If a model has no reliable reasoning
capability metadata, DeepSpace leaves its provider default in place and does not
invent effort choices.

For LarpRouter, verified DeepSeek V4.1 Flash routes expose Low, High, and Max,
default to High, and allow thinking to be disabled. Verified GLM-5.3 routes
expose Low, High, and Max, default to Max, and do not support disabling
thinking. The adapter sends the selected route's native `reasoning_effort`
value and preserves the provider's default when reasoning controls are not
selected. Other LarpRouter model IDs remain on their advertised capabilities or
provider defaults.

Model narration emitted before a tool call or `ask_user` pause is persisted as
an ordered activity step. A paused, resumed, cancelled, or reloaded turn keeps
that narration beside the tool and question events instead of rebuilding the
turn from only its final answer.

### Provider continuation and task resume

DeepSeek requires the exact `reasoning_content` returned by a thinking-mode
assistant turn to be sent on its follow-up request, including when the model is
served through an OpenAI-compatible gateway. DeepSpace captures the protocol
field separately from the redacted thinking shown in activity. It encrypts
each continuation with the configured provider-secret crypto backend and
binds it to the tenant, user, conversation, assistant message, and model turn.
History and activity API responses never return the encrypted continuation.
If encryption is unavailable, DeepSpace stops before executing a tool rather
than storing the continuation as plaintext.
For DeepSeek V4, the adapter also omits `tool_choice` while thinking is on and
sends non-null assistant content on tool-call messages, as required by the
[DeepSeek thinking-mode](https://api-docs.deepseek.com/guides/thinking_mode/)
and [V4 integration guidance](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/).

DeepSpace restores continuations for later conversation turns, tool follow-up,
clarification, approval, and queue retry. The short-lived history cache keeps
only message text and the encrypted continuation reference needed to restore
it; it never stores plaintext reasoning. If an older checkpoint or a gateway
response has no continuation, DeepSpace rebases the
affected assistant/tool exchange as quoted historical context, includes any
saved successful tool result, and tells the model not to repeat completed
actions. Queue retry continues from those saved results and does not rerun a
completed external action. This recovery applies only to DeepSeek-protocol
requests; other providers do not receive DeepSeek's private field.

A failed-turn retry remains anchored to the original saved user prompt;
clarification and approval resumes include that prompt even if it is older than
the normal 20-message history window. Context compaction protects the original
task and the current clarification answer.

## Productivity tools

The native capability catalog contains the explicit-target workspace tools
`read`, `find`, `write`, `edit`, and `delete`; the unified task lifecycle tool
`todo_write`; document comparison through
`analyze(operation="compare_documents")`; current web tools `web_search`,
`url_read`, and `image_read`; bounded `sandbox_execute` and `artifact_create`;
and `ask_user`. The catalog exposes descriptions first, then loads only exact
selected schemas. There are no separate `document_read`, `document_query`,
`document_compare`, `todo_read`, `todo_mark`, `todo_check`, `observe`, or `final` tools.

Workspace operations are scoped to the active user, tenant, and conversation.
URL and image tools use server-side HTTP with timeouts, redirect
limits, DNS/IP private-network blocking, domain allowlists, response-size
limits, and provider/user rate limiting. The model never receives shell,
terminal, arbitrary cURL, filesystem, or file-explorer access.

### Current-turn Library attachments

Before a chat request uses an attachment, DeepSpace verifies that the file
belongs to the authenticated tenant, user, and conversation. The model receives
authorized file names and IDs as context and discovers the appropriate read,
query, compare, or sandbox schema from the catalog. Attachment context alone
does not grant Library write or delete tools; those still require the matching
user request and existing tool policy.

Attached images are sent as visual inputs only when the selected model advertises
or is known to support image input. DeepSpace verifies the image signature and
limits direct visual input to 10 images and 12 MiB total. If image bytes are
unavailable, exceed the limit, or the model has no image capability, DeepSpace
uses text extracted during upload where available and tells the model when OCR
found no readable text. If a provider rejects an attached image with a specific
image-modality error before it returns output, DeepSpace retries that request
once without image bytes and with the saved OCR text. It does not use this
fallback for authentication, rate-limit, network, or unrelated request errors.
OCR text is treated as untrusted file content. A file’s name alone is never
treated as its contents.

The Library stores an extraction status with the file and completed upload:
whether text was extracted, no readable text was found, extraction was
unavailable, and whether OCR or layout vision ran. The composer shows only this
summary; the completed-upload status response does not include extracted text.

For documents, `read(target="library", operation="read")` returns saved
extraction/OCR text and `read(target="library", operation="query")` performs
bounded hybrid retrieval for targeted evidence or large files. The query result
reports whether embeddings and reranking actually ran; a direct read is not
described as RAG. `analyze(operation="compare_documents")` performs exact
text comparison. Supported raster images embedded in Office files are OCR'd
directly within bounded image-count and byte limits, so scanned inserts can
supplement substantial native text. The existing LibreOffice-to-PDF OCR
fallback remains available for sparse Office files and embedded formats the
direct image path cannot read.

## MCP-connected productivity tools

MCP is an optional, conversation-scoped extension of the DeepSpace tool
registry. It does not replace or bypass the existing MCP integration. A tool
is exposed to DeepSpace only when all of the following are true:

- the MCP server belongs to the authenticated tenant and user;
- the server is enabled, connected, backed by an approved provider, and has a
  discovered catalog. If its cached catalog is old, the last known catalog
  remains available while a background refresh is requested;
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

Catalog refreshes advance the tool revision only when the normalized tool
definitions actually change; harmless refreshes and tool ordering changes do
not invalidate an in-progress run. If a real change happens while DeepSpace is
working, the bridge reloads that server's current cached tools by its
tenant/user-owned server ID, then checks the current schema, policy, risk, and
approval before execution. A removed or renamed tool is not called; DeepSpace
is told to search again and load its current schema. An approval is bound to
the catalog revision shown in its request. If that revision changes while the
approval is pending, the old approval expires and the action does not run.

Catalog discovery remains asynchronous so routine MCP calls do not wait for a
remote catalog request. During refresh, DeepSpace can use the last known
catalog; each tool search reloads the latest catalog persisted by a completed
refresh, and schema lookup reloads the selected server before returning its
schema. An aged catalog queues a background refresh without blocking the
request. The revision and execution checks prevent an old binding from being
executed after a newer catalog has been committed. Until that refresh completes,
the last known catalog may be shown; a remote provider changing its catalog is
not visible until the provider responds successfully. Successful model output
is bounded by `DEEPSPACE_MCP_MAX_RESULT_CHARS` so a large remote page cannot
refill the conversation context unexpectedly. These rules live in the shared
MCP broker and apply to every tool-capable model provider.

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

The existing `POST /api/v1/deepspace/chats/{conversation_id}/cancel` route
sets the durable cancellation flag before it attempts to publish the optional
Redis cancellation marker. The stream polls both signals while waiting for a
provider chunk, so a cache outage cannot turn a persisted Stop request into a
failed HTTP request or leave the browser waiting indefinitely. The client keeps
the stream attached briefly for the worker's terminal event, then reconciles
saved history if that event never arrives.

### Durable composer queue

An active DeepSpace response never disables the composer. A normal additional
message is persisted in `deepspace_queued_turns` and dispatched in FIFO order
after the active turn reaches a terminal state. **Steer** persists the new
message at priority and asks the active run to cancel; it does not depend on a
browser tab remaining open. Each record stores the submitting tenant, user,
conversation, request id, and an authorization snapshot. Queue reads, removal,
and dispatch are all scoped to that same tenant/user/conversation boundary.

Queue state reports an ID as active only after a dispatcher has claimed the
turn (or a durable runtime row confirms it is active). The next queued ID is
not an active run and clients must not attach an event stream to it yet. Queue
dispatch tasks use the bounded `deepspace_control` worker queue, separate from
the long-running `deepspace` model tasks; both worker services must be running
for prompt dispatch and generation.

A worker marks a turn complete only after it receives a durable `done` event;
an `error` event fails the turn. If a stream exits without either event, the
worker closes the run and assistant message as failed and publishes a retryable
terminal error. Queue recovery also reconciles an old active runtime row when
its matching queue turn is already terminal and its heartbeat is stale. It
does not release a turn whose queue record is still running merely because a
provider response is taking a long time.

A failed turn is terminal but does not pause the conversation queue. Its error
and prompt stay visible while the dispatcher advances to the next queued item,
ordered by priority and then FIFO sequence. Users can retry a failed prompt as
a separate attempt. The retry continues from retained runtime checkpoints when
available; if that runtime data has expired, it restarts from the saved prompt
and the original Library attachment references, and clearly warns that
completed external actions could run again. The retry is a new linked queue
record; the failed attempt remains in history. **Resume queue** only clears a
user pause and starts the next queued item; it never silently retries a failed
prompt. Legacy automatic failure pauses are cleared by queue recovery, while an
explicit user pause is always preserved.

The queue API is:

- `GET /api/v1/deepspace/chats/{conversation_id}/queue`
- `POST /api/v1/deepspace/chats/{conversation_id}/queue`
- `PATCH /api/v1/deepspace/chats/{conversation_id}/queue/{client_request_id}`
- `POST /api/v1/deepspace/chats/queued/{client_request_id}/cancel`

The PATCH route edits only a turn that is still `queued`. It uses the same
tenant, user, conversation, and `queries:run` boundaries as queue submission;
`expected_prompt` prevents a stale editor from overwriting a newer change. The
turn keeps its request id, sequence, priority, authorization snapshot, runtime
settings, and Library attachment references, so its FIFO or steered position
does not change. A turn claimed by a worker, a terminal failed attempt, or a
prompt changed in another editor returns `409`; the client keeps the user's
edited text in the composer for recovery. Existing queue attachments are
preserved and are not editable from this prompt editor.

The initial normal stream is also first persisted as a queue turn. A browser
refresh reconnects to the durable event stream, while the queue continues in
the worker. Approval and clarification resumes deliberately reuse the original
request id, preserving their queue slot rather than leaving a paused turn that
could block later messages.

Regeneration uses the same durable queue and event stream. The queue record
retains the target assistant message id, the source prompt, and its Library
attachment references. The worker creates a new answer version only when the
regeneration starts, so the existing answer remains visible while it waits.
Users can queue a regeneration while another reply is running; it starts in
conversation order without detaching the current browser stream. Regenerating
an older reply anchors the model context at that reply's source prompt, so
later turns are not included. Repeated delivery of one queue request id
replays its saved events and does not create another generation. Queued
regenerations can be canceled or retried, but their source prompt cannot be
edited.

Editing the latest completed user prompt creates a new active prompt version and queues a
regeneration for its existing assistant message in one database transaction. The stream endpoint
then reconnects to the durable queue event log. Reusing an edit request id with the same prompt
replays that attempt; using a new id after a completed generation creates another prompt version
and queued response. The API rejects stale prompt targets before writing a version. The client only
offers this action when the latest prompt is editable and no queue work is pending.

### Clarification ownership and fresh requests

An `ask_user` card is an explicit continuation control, not a mode that takes
over the chat composer. Selecting one of that card's choices, or submitting
text through its **Other / write my own answer** field, sends the card's exact
`resume_user_question_id` and continues the paused run. The server then claims
that question once, scoped to its tenant, user, and conversation.

The resumed browser subscription starts immediately after the durable pause
event. It does not replay that old terminal `awaiting_user` frame, because a
browser SSE reader would correctly close at that frame and miss the new answer.
The continuation therefore appears live without a refresh; its full event log
and final response remain durable for reconnect and recovery.

Every message sent through the normal composer is always a fresh user request.
The client never infers that composer text answers an older question from its
wording. Thus `hello, how are you?`, a new research request, or any other text
cannot accidentally inherit a prior task's question, tool arguments, plan, or
state. If an older clarification is still open, it remains visible for an
explicit answer; the new composer request follows normal durable queue ordering
rather than silently changing the older run.

Database migrations include:

- `alembic/versions/20260726_0002_deepspace_agent_runtime.py`
- `alembic/versions/20260916_0001_deepspace_queued_turns.py`
- `alembic/versions/20260916_0002_deepspace_request_metrics.py`
- `alembic/versions/20260917_0001_cascade_deepspace_runtime_and_snapshots.py`
- `alembic/versions/20260918_0001_deepspace_context_summaries.py`
- `alembic/versions/20260920_0001_deepspace_context_epochs.py`
- `alembic/versions/20260922_0001_deepspace_queue_controls.py`
- `alembic/versions/20260923_0001_deepspace_checkpoint_retries.py`
- `alembic/versions/20260924_0001_tenant_storage_allocations.py`
- `alembic/versions/20260925_0001_storage_retention_lifecycle.py`
- `alembic/versions/20260926_0001_storage_reservations_archive_reconciliation.py`
- `alembic/versions/20260927_0001_retention_checkpoints.py`
- `alembic/versions/20260928_0001_retention_protections_and_run_links.py`
- `alembic/versions/20261012_0016_deepspace_queued_regenerations.py`

The queue, metrics, cascade, context, storage, retention, and protection
changes described here were present in the locally verified snapshot recorded
on 2026-09-27. Later migrations and current deployment status are tracked in
the [release index](../release/03-current-worktree-change-index.md). The
historical local migration, regression, and restore results do not establish
that staging or VPS rollout is complete.

This runtime does not modify Query, terminal, file-explorer, connector, or
operating-system storage behavior. It adds only the DeepSpace adapter and the
approval/resume path described above; the existing MCP transport and security
boundary remain unchanged.

### Legacy provider-profile OAuth continuity

This token-refresh path applies to existing provider-profile OAuth connections
that remain installed; it is separate from new Composio-hosted Marketplace
connections, which use each account's Composio key and encrypted hosted-session
reference as described below.

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

Composio-hosted MCP apps use the live Composio catalog in the MCP Marketplace.
Each user enters their own encrypted project key under Providers → MCP. The
key row and encryption associated data are scoped to that tenant and account;
the running backend decrypts it to call Composio. App identities are derived
from the current tenant and account UUIDs, and each connected app's session ID
is encrypted with tenant/user/server associated data. Composio verifies the
one-time OAuth callback against that same user identity. Composio and the app
provider process tool inputs and results, so those requests are not
end-to-end encrypted from the server or those providers.

For Composio, newly connected policies permit reads under the saved policy and
require approval before writes, deletions, or external messages. A per-tool
Always allow setting cannot bypass the runtime's side-effect approval check.
The connector catalog, user setup, callback prerequisites, and
privacy boundaries are documented in
[`../capabilities/mcp/03-composio-hosted-mcp.md`](../capabilities/mcp/03-composio-hosted-mcp.md).

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
## Desktop local model relay

LM Studio and Ollama can be selected with `metadata_json.runtime_target` set to
`desktop`. The provider registry then uses the authenticated Electron runtime
relay instead of making the backend call a loopback address. The relay accepts
only loopback URLs and normalizes chat, model discovery, health, embedding, and
Ollama pull results into the provider contracts. The existing one-use ticket,
single-owner WebSocket, Redis request queue, frame limits, and cancellation
path are shared with the Codex desktop bridge. Omitting `runtime_target` keeps
the existing server-side LM Studio/Ollama path unchanged.
