# 12. DeepSpace low-latency execution

## 1. Problem

Interactive DeepSpace turns can involve several provider calls: a planning
call, one or more tool calls, and a grounded answer call. A slow upstream
stream can therefore make a normal request appear frozen even when the API,
worker, and browser are healthy.

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
The cancellation watcher enforces that budget even when an upstream SSE
connection stops producing events without closing. This is transport safety,
not a model output limit.

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

## 6. Adaptive native-tool profiles

DeepSpace keeps its complete authorized capability set, but does not send every
native tool schema for clear, narrow requests. The server selects a conservative
profile before the first provider round:

- social greetings: direct response, no native tools;
- Library/document requests: authorized discovery, read, query, compare, and
  analysis tools;
- tabular/data requests: the Library profile plus authorized sandbox/artifact
  tools;
- explicit workspace edits: note/Library read-find-write-edit-delete tools.

Ordinary requests default to the direct profile; the full native set is reserved
for an explicit multi-step agent request. MCP schemas remain strictly routed by
the existing conversation-scoped MCP policy and are additive
to the native profile; this routing never grants a new tool or bypasses tenant,
user, approval, catalog, or encryption boundaries.

The stream emits the selected `toolProfile` and `toolSchemaCount` in its metrics
event and persists the profile in assistant metadata. These values are
observability metadata, not user content or authorization state.

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

See `deepspace-operations-runbook.md` for the safe retry, staging load, browser
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
context. Diagnostics may say cache *eligible*; only provider usage fields may
later report a verified cache hit.
