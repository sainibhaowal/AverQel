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
