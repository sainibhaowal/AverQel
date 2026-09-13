# 12. DeepSpace low-latency execution

## 1. Problem

Interactive DeepSpace turns can involve several provider calls: a planning
call, one or more tool calls, and a grounded answer call. A slow upstream
stream can therefore make a normal request appear frozen even when the API,
worker, and browser are healthy.

## 2. Fast mode

Fast mode is enabled by default and is provider-independent:

1. Tool-planning rounds use the smaller of `AKS_LLM_MAX_TOKENS_PER_REQUEST`
   and `AKS_DEEPSPACE_TOOL_PLANNING_MAX_TOKENS` (default `1536`).
2. A round after a tool result uses
   `AKS_DEEPSPACE_FINAL_MAX_TOKENS` (default `4096`) so grounded answers can
   remain detailed.
3. Every provider stream receives a bounded read budget from
   `AKS_DEEPSPACE_PROVIDER_READ_TIMEOUT_SECONDS` (default `90`, maximum `300`).
4. The cancellation watcher enforces that budget even when an upstream SSE
   connection stops producing events without closing.
5. Existing durable Celery execution, tool policy, authentication, tenant
   isolation, retries, and recovery remain unchanged.

## 3. Configuration

```dotenv
AKS_DEEPSPACE_FAST_MODE_ENABLED=true
AKS_DEEPSPACE_PROVIDER_READ_TIMEOUT_SECONDS=90
AKS_DEEPSPACE_TOOL_PLANNING_MAX_TOKENS=1536
AKS_DEEPSPACE_FINAL_MAX_TOKENS=4096
```

Set fast mode to `false` only when a workload explicitly requires the old
maximum output budget. A provider that needs more time can raise the read
timeout, but the value remains bounded by the application validation rules.

## 4. What this does not change

1. It does not disable tools, document retrieval, OCR, RAG, citations, MCP,
   sandbox execution, artifacts, or scheduled jobs.
2. It does not expose provider credentials or change authorization boundaries.
3. It does not cancel durable work based on the interactive budget; it only
   ends a stalled provider attempt so the existing safe error/retry path can
   run.

## 5. Verification

1. Run the backend DeepSpace unit tests and provider adapter tests.
2. Send a simple chat prompt and confirm the first model response uses the
   configured provider.
3. Send a tool prompt and inspect the request metadata in a redacted debug
   log: the first round should use the planning budget and subsequent rounds
   should use the final budget.
4. Temporarily point a test provider at a stream that never emits data and
   confirm the request terminates at the configured read budget rather than
   waiting indefinitely.
