# 01. DeepSpace low-latency execution

## 1. Problem

Interactive DeepSpace turns can involve several provider calls: a planning
call, one or more tool calls, and a grounded answer call. A slow upstream
stream can therefore make a normal request appear frozen even when the API,
worker, and browser are healthy.

### Stream path and speed boundary

Provider adapters request the provider's native streaming protocol, including
OpenAI-compatible Chat Completions, Anthropic Messages, Google streams, and
LM Studio-compatible local endpoints. For detached runs, the worker assigns
each received frame one sequence number, places it on a bounded live Redis
queue, and writes durable replay rows in short batches on a separate database
session. A database commit is therefore not placed between provider chunks.
Prepared chat state, including any newly recorded context epoch, is committed
before each provider stream begins so a slow model cannot hold tenant database
locks while it generates or waits for network input.
The browser replays PostgreSQL once when it subscribes and uses Redis for the
live path, with an infrequent durable-gap check for recovery. Terminal frames
are durable before they are published.

This removes AverQel's per-frame persistence overhead; it cannot make an
upstream model generate faster. During a live browser stream, the composer
shows a client-side character-based output estimate and an average estimate
that refreshes as chunks arrive. That value includes answer, reasoning, and
streamed function-argument chunks and is labeled as an estimate because the
provider tokenizer and final usage are not available yet. After the stream completes, the displayed
provider generation rate uses the exact provider-reported output tokens when
available and the server-observed interval between provider output events.
TTFT also includes routing, context preparation, tools, and provider startup.
Buffered providers or models that emit one large response will still report
the speed of the output they actually provide, or explain why an exact rate
is unavailable.

## 2. Provider-owned output budgets

DeepSpace does not impose a fixed output-token budget on interactive model
calls. During provider model discovery, AverQel records an explicitly
advertised output limit (when the provider exposes one) and sends that exact
model limit. If no limit is advertised, `max_tokens`/`max_output_tokens` is
omitted and the provider applies its own documented default. The context
compactor may reserve a small local allowance to avoid prompt overflow, but
that reservation is not sent as an output cap and does not truncate a response.

Every provider stream still receives a bounded idle-read budget from
`AKS_DEEPSPACE_PROVIDER_READ_TIMEOUT_SECONDS` (default `90`, maximum `300`).
The cancellation watcher checks both the request's Redis cancellation marker
and the durable run flag while an upstream SSE connection is idle. The Redis
marker is written before the API updates run and queue rows, so the worker can
stop promptly even when that database update receives a retryable `503`. This
is transport safety, not a model output limit.

Queue submissions use a stable client request ID and are idempotent for that
conversation and user. The web client retries a `503` once using the same ID
and the server's `Retry-After` value, so a transient database interruption does
not create a duplicate prompt. Stop requests follow the same bounded retry
rule. The browser keeps the event stream attached until the worker publishes a
durable terminal event; closing the browser reader alone is not treated as a
confirmed cancellation. Queue recovery also reconciles an expired worker
lease for a turn already marked `cancelling`, persists its terminal cancelled
event, and clears the assistant message's active state so the browser does not
leave a stopped run spinning indefinitely.

## 3. Configuration

```dotenv
AKS_DEEPSPACE_PROVIDER_READ_TIMEOUT_SECONDS=90
```

The old planning/final output-token settings were intentionally removed. They
were application heuristics and could truncate a capable model.

## 4. What this does not change

1. It does not disable tools, document retrieval, OCR, RAG, citations, MCP,
   sandbox execution, artifacts, or scheduled jobs.
2. It does not expose provider credentials or change authorization boundaries.
3. It does not cancel durable work based on an output budget; it only ends an
   idle provider attempt so the existing safe error/recovery path can run.
4. Provider adapters still honor protocol-required fields. For example, the
   Anthropic Messages API receives its adapter-required default when no limit
   is advertised; this is not used for OpenAI-compatible or OpenCode requests.

## 5. Verification

1. Refresh provider models and inspect the redacted model-cache capabilities.
2. A model with an advertised output limit receives that exact value.
3. A model without one receives no `max_tokens` override, allowing its
   provider/model default to apply.
4. Run a simple prompt and a tool prompt, then verify the selected provider in
   the DeepSpace activity timeline.
5. Point a test provider at a stream that never emits data and confirm the
   request terminates at the configured idle-read budget rather than waiting
   indefinitely.

## 6. Dynamic native-tool discovery

DeepSpace starts with one compact `discover_tools` schema instead of sending
every native schema or selecting a fixed keyword profile. When a model needs a
capability, it requests the bounded catalog of native tools authorized for
that request. The model then selects exact catalog names, and the backend loads
only those full schemas for the next provider round. A later step can discover
additional capabilities in the same conversation. Tool selection therefore
uses the model's understanding of the request and the catalog descriptions,
not a hard-coded intent-to-tool keyword table.

The broker can return only names in the request's authorized native registry.
Loaded schemas still pass through typed argument validation, the runtime
allowlist, tenant/user/conversation-scoped handlers, cancellation, and existing
side-effect policy. The initial interface does not change permissions or
MCP's live conversation-scoped broker. MCP discovery and exact schema loading
remain separate because those schemas and references are owned by each
connected server.

Direct conversational answers can use no tools. Substantial multi-step work
uses a persisted task plan only when the model determines that ordered,
independently verifiable steps are needed. The runtime verifies the saved task
ledger and returns to ordinary assistant text; it has no separate `observe` or
`final` tool and does not insert a synthetic user message. Tool profile
telemetry now reports only `dynamic` or `direct`; it is operational metadata,
not authorization state.

Simple direct-response prompts also use a compact safety policy. The full
DeepSpace policy remains enabled for Library, data, edit, MCP, research, and
ambiguous work. This reduces unnecessary baseline context without removing
capabilities from requests that need them.

## 7. Request-stage telemetry

Each completed or failed provider turn writes one tenant- and user-scoped
`deepspace_request_metrics` record. It contains only operational facts:
provider/model identity, terminal outcome, total latency, time to first output,
the selected native-tool profile, and a redacted error code. It never stores a
prompt, response, tool arguments, citations, API key, or provider secret.

`GET /api/v1/deepspace/chats/operational-summary` is permission-protected by
`queries:run` and returns only the caller's tenant/user aggregate: sample count,
failure rate, and p50/p95 latency per provider/model. This endpoint is suitable
for the existing private DeepSpace operations card. It does not require an
 external monitoring service.

The stream also emits truthful lifecycle states (`resolving_provider`,
`provider_ready`, and `finalizing`) and metrics (`requestLatencyMs`,
`timeToFirstTokenMs`). A lifecycle event describes a completed server action;
it is never synthesized as hidden model reasoning or fake progress.

## 8. Operations rollout and guardrails

Deploy the migration before enabling the operations UI. Alert on sustained
failure rate, p95 request latency, and a rising provider timeout count, grouped
by tenant-safe provider/model dimensions. Use the existing provider-health
checks for provider availability; do not expose raw health logs or provider
credentials to the browser. Capacity work must set queue concurrency and
provider read deadlines from measured p95/p99 values, then validate with
authenticated browser tests and concurrent API load tests in a staging tenant.

See `05-deepspace-operations-runbook.md` for the safe retry, staging load, browser
validation, rollback, and capacity-change procedures.

OpenCode Zen compatibility: DeepSpace sends a stable `x-opencode-session` value
derived from the conversation, keeps the legacy `X-Session-ID` header for older
gateway deployments, and identifies itself with an AverQel DeepSpace
user-agent. These headers support OpenCode's external-agent routing for models
that OpenCode permits; they do not bypass account, model, or usage policy.

## 9. Provider-aware context transport and durable compaction

DeepSpace owns the portable behavior for every chat provider: compact policy,
selected tools, recent raw turns, durable transcript, Library/MCP authorization,
and user-visible conversation telemetry. A provider cache is an optional
transport optimization, never a requirement for correct behavior.

- Anthropic Messages requests use documented ephemeral `cache_control` when
  `AKS_DEEPSPACE_PROVIDER_PROMPT_CACHING_ENABLED=true` (the default).
- Gemini requests retain a stable prefix and can use Gemini's native implicit
  caching. Explicit Gemini cached-content objects are not created until a
  separate lifecycle, TTL, and deletion implementation is deployed.
- OpenAI-compatible, local, and custom Chat Completions endpoints receive no
  Responses-only cache or state fields. They use the same DeepSpace compact
  fallback, avoiding compatibility failures.

After more than six raw messages, DeepSpace writes a tenant/user/conversation
scoped, bounded reference summary to `deepspace_conversation_context_summaries`.
It is deterministic, marks itself as reference-only, is never treated as an
instruction, and is deleted automatically with its conversation through the
database foreign key cascade. The complete transcript remains the source of
truth. This avoids a second model call merely to summarize context and works
identically with hosted and self-hosted providers.

The composer separates user-visible conversation tokens from internal request
context. The diagnostics panel labels its latest-round context separately from
the cumulative serialized estimate for the whole turn. A turn can contain
several model requests when tools or recovery steps run. Provider usage is
shown with its scope (currently the latest reported model round). When every
round reports a field, the panel also shows an exact provider turn total;
otherwise that field is marked incomplete. Adapters that do not return usage,
including many local runtimes, remain explicitly marked as
unreported rather than being assigned a fabricated tokenizer count. Ollama
native `prompt_eval_count`/`eval_count` fields are normalized alongside the
OpenAI-compatible, Anthropic, Gemini, and Codex usage shapes. Diagnostics may
say cache *eligible*; only provider usage fields may later report a verified
cache read or write.
