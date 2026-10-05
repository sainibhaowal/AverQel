# 02. DeepSpace Agent Harness: Production Implementation Plan

## Objective

Evolve DeepSpace from a provider-facing tool-calling loop into an adaptive,
typed capability runtime without changing its authorization, tenant isolation,
MCP approval, durable-run, or existing API guarantees.

## Current system and preserved strengths

- `app/deepspace/services/chat_service.py` owns native tool definitions,
  request profiles, provider rounds, lifecycle enforcement, and execution
  dispatch.
- `app/deepspace/services/mcp_tool_broker.py` already provides the correct
  compact broker pattern for dynamic MCP catalogs: exact references, bounded
  schemas, bounded results, and no direct upstream tool exposure.
- `app/deepspace/services/mcp_bridge.py` and
  `app/integrations/services/mcp_runtime.py` remain the authority for MCP
  account ownership, policy, approval, catalog revision checks, and exact
  JSON-schema validation.
- `app/deepspace/services/runtime_store.py` remains the durable run,
  checkpoint, cancellation, and event-history authority.
- Existing in-progress context epochs, result references, metrics, provider
  usage normalization, migration, and frontend work are baseline changes and
  must not be reverted or overwritten.

## Non-negotiable invariants

1. The model never selects a tenant, account, server transport, permission,
   approval outcome, or unscoped MCP tool.
2. Native and MCP tool arguments are validated before execution; MCP retains
   its existing authoritative upstream schema validation.
3. Write, delete, publish, send, and other side-effecting calls remain
   serialized and approval-gated exactly as they are today.
4. Read-only concurrency remains bounded by existing runtime settings.
5. Existing SSE event names, API payloads, task lifecycle ordering, durable
   checkpoints, storage, encryption, and auth scopes remain compatible.
6. A registry or cache failure must fail closed for execution and fall back to
   the known-safe current tool bundle; it must never broaden tool access.

## Implementation sequence

### Phase 1 — Typed native tool catalogue and compatibility emitter

Create `app/deepspace/services/tool_registry.py`.

- Add immutable `ToolSpec` metadata: name, Pydantic argument model,
  description, mode, schema version, idempotency/concurrency metadata, and
  model-facing schema.
- Add `ToolRegistry` lookup, allowlisted emission, schema digesting, and
  native argument validation.
- Register every current native tool. The shared OpenAI-compatible tool shape
  remains the input to existing provider adapters, so Anthropic, Google, and
  OpenAI-compatible integrations retain their current contracts.
- Replace `PRODUCTIVITY_TOOLS` construction and direct web-tool emission in
  `chat_service.py` with registry emission. Keep compatibility aliases only
  while tests and downstream imports need them.

Files:

- `app/deepspace/services/tool_registry.py` (new)
- `app/deepspace/services/chat_service.py`
- `app/deepspace/services/runtime_policy.py`
- `tests/unit/test_deepspace_tool_registry.py` (new)
- `tests/unit/test_deepspace_tool_profiles.py`
- `tests/unit/test_deepspace_chat_service.py`

### Phase 2 — Authoritative native argument validation

- Validate a parsed native tool payload only after the current-round allowlist
  is determined and before policy evaluation or execution.
- Return a concise structured tool error on validation failure; do not execute
  a handler and do not retry a write with modified arguments.
- Preserve MCP broker handling and MCP's independent JSON-schema validation.

Files:

- `app/deepspace/services/chat_service.py`
- `app/deepspace/services/tool_registry.py`
- `tests/unit/test_deepspace_chat_service.py`

### Phase 3 — Hard per-category context controls

Create `app/deepspace/services/context_budget.py`.

- Measure the effective serialized request and reserve output plus a safety
  margin before every provider call.
- Allocate bounded pools for history and tool results after reserving policy,
  the current user request, tool protocol/schema, output, and safety margin.
- Enforce the history pool by selecting complete, newest-first conversation
  turns. Enforce the result pool by replacing oversized model-visible results
  with a bounded preview/reference envelope. Never split an assistant tool
  call from its tool response.
- Feed the actual preview budget into both MCP and native result-reference
  paths. Existing absolute MCP and provider limits remain upper bounds.
- Keep all existing hard limits as upper bounds. The controller only shrinks
  untrusted/optional context; it cannot remove the user message, policy,
  approval state, or required tool protocol.

Files:

- `app/deepspace/services/context_budget.py` (new)
- `app/deepspace/services/chat_service.py`
- `app/core/config.py` (only additive bounded settings if needed)
- `tests/unit/test_deepspace_context_budget.py` (new)
- `tests/unit/test_deepspace_chat_service.py`

### Phase 4 — Result references beyond MCP

- Create a generic tenant/user/conversation-scoped, opaque, short-lived
  `ToolResultStore`; retain `MCPResultStore` as a compatibility wrapper.
- Add a compact `get_tool_result` native read tool only after a native result
  reference exists. It resolves only same-scope values and returns a bounded
  slice. MCP continues to use `mcp_broker(operation=result)` unchanged.
- Preserve complete private execution results in their existing durable
  systems; only the model-visible representation becomes a preview/reference
  envelope. Store the post-policy payload, never a bypass of output filtering.
- Do not reference interactive, approval, final-answer, or already-small
  results. Result-reference retrieval must not broaden tool authorization.

### Phase 5 — Explicit runtime transitions and safe parallel execution

- Extract legal run phases and checkpoint construction into
  `runtime_transitions.py`. The service keeps the current runtime store and
  SSE names, but transitions become explicit, validated, and replayable:
  `context_assembled → model_requested → actions_validated →
  awaiting_approval|executing → results_recorded → finalizing`.
- Add a dependency-aware execution planner. A contiguous read-only run is an
  ordered parallel batch; every write/interactive call is a barrier and runs
  alone in model order. This preserves ordering around side effects and fixes
  the prior possibility of a later read racing an earlier write.
- Approval checks occur before a planned write enters execution; cancellation
  and deadline checks remain in each underlying tool call.

### Phase 6 — Replay/canary traces and budget visibility

- Record sanitized, durable runtime trace steps for context allocation, tool
  profile selection, execution batch shape, and terminal result. Trace data
  contains counts, digests, modes, and budgets—not prompts, secrets, raw tool
  payloads, or approval tokens.
- Add a non-authoritative canary calculation that compares the selected native
  tool profile with the registry's emitted digest/count. It is observability
  only: it never changes a provider request, permissions, or execution.
- Emit the new budget and trace fields through the existing `metrics` SSE
  event. Extend the existing frontend `MessageMetrics` typing and context
  inspector; no new API route or client persistence format is required.

## Explicit non-goals for this change series

- No model-controlled permissions or automatic approval.
- No live self-modifying prompts/RL policy optimizer.
- No speculative external writes.
- No assumption that provider schema caching removes wire/token cost.
- No database or frontend API breaking change.

## Verification

Run focused unit tests after each phase, then backend unit tests and relevant
frontend stream/protocol tests. Validate migration/model registration and
provider payload snapshots. Inspect the final diff to ensure no unrelated
worktree changes were modified.

## Implementation status recorded by this plan

The phase summary below records work reported when this implementation plan
was completed. Verify behavior against the current source before relying on a
specific detail; this section is not a current deployment or release-status
record. See the [current release index](../release/03-current-worktree-change-index.md).

Implemented in this change:

- Phase 1 compatibility registry, typed contracts, schema digests, and
  defensive provider-schema emission for every native DeepSpace tool.
- Phase 2 native argument validation after current-round capability selection
  and before policy/execution. MCP continues to use its independent exact
  upstream schema validation.
- Phase 3 hard controls: protected policy/schema/current-user/output
  reservations, ordinary-history trimming that preserves tool protocol pairs,
  and a bounded per-round native/MCP result representation.
- Phase 4 scoped native result references via `ToolResultStore`, with a
  dynamically exposed read-only `get_tool_result` continuation tool. MCP
  reference retrieval remains unchanged.
- Phase 5 explicit validated checkpoint transitions for model/action/execution
  boundaries and ordered execution batches: contiguous native reads run in
  parallel; dynamic MCP and all side-effecting calls remain conservative
  serial barriers.
- Phase 6 sanitized runtime batch traces and budget/canary telemetry through
  the existing metrics SSE contract, with frontend metric typing.
- A compatibility guard for context-epoch telemetry on non-SQLAlchemy test
  doubles and an MCP broker `result` policy-path correction.

These phases were implemented through additive, compatibility-preserving
seams. They do not change routes, database schema, provider request contracts,
tenant scopes, approvals, or existing MCP broker semantics. Verification
includes focused tests, the DeepSpace/MCP regression suite, all `unit_no_db`
tests, frontend lint/type invocation, Python compilation, and `git diff
--check`.

## Follow-up production-hardening plan

The following work is intentionally separate from the core runtime change. It
improves tuning, operations, confidence, and maintainability without changing
the user-facing chat protocol.

### A. Model/workload-aware budget tuning

What: Replace one fixed history/result ratio with a bounded policy selected by
verified context-window tier and workload class. Unknown windows retain the
current conservative behavior. Add floors for the current conversation and
answer space, and never exceed the provider window.

Why: A research turn benefits from result capacity, while a conversation or
coding turn benefits from history and tool/error context. One ratio is safe but
not optimal for every model.

Where:

- `backend/app/deepspace/services/context_budget.py`
- `backend/app/deepspace/services/chat_service.py`
- `backend/app/core/config.py` only for additive bounded defaults
- `backend/tests/unit/test_deepspace_context_budget.py`
- `backend/tests/unit/test_deepspace_chat_service.py`

### B. Production canary metrics, dashboard, and alerts

What: Add low-cardinality Prometheus counters/histograms for budget decisions,
native-result references, batch plans, and canary mismatches. Extend the
existing admin `/metrics/summary` response and dashboard. Add alert rules to
the existing `backend/monitoring/prometheus/deepspace-alerts.yml`.

Why: Metrics already reach the SSE/frontend path, but operators need trend and
alert visibility without exposing tenant, prompt, tool-argument, or secret
labels.

Where:

- `backend/app/system/services/metrics_service.py`
- `backend/app/system/api/metrics.py` and its existing schema only if needed
- `backend/app/deepspace/services/chat_service.py`
- `backend/monitoring/prometheus/deepspace-alerts.yml`
- `backend/tests/unit/test_deepspace_metrics.py`
- `backend/tests/security/test_metrics_no_sensitive_labels.py`
- `frontend/app/dashboard/admin/metrics/page.tsx`

### C. Anonymized production replay fixtures

What: Add checked-in synthetic/anonymized trace fixtures and a replay harness
for context allocation, native references, MCP discovery/approval, batch
ordering, cancellation, and malformed arguments. Fixtures contain no raw user
text, tokens, URLs with credentials, file contents, or tenant identifiers.

Why: Unit tests prove individual mechanics; replay fixtures prove realistic
multi-round behavior and prevent regressions in the long `stream_turn()` path.

Where:

- `backend/tests/fixtures/deepspace_replay/*.json`
- `backend/tests/unit/test_deepspace_replay.py`
- `backend/app/deepspace/services/replay_trace.py` only if a reusable parser
  is needed
- `backend/docs/deepspace/02-deepspace-agent-harness-implementation-plan.md`

### D. Incremental `stream_turn()` orchestration extraction

What: Extract one pure boundary at a time—budget/context assembly, action
validation, batch execution, and result materialization—behind the existing
method. Keep the existing SSE generator, runtime store, database writes, and
provider request objects as the compatibility boundary.

Why: Smaller methods improve testability and recovery without risking a
large one-shot rewrite of a 7,000-line service.

Where:

- `backend/app/deepspace/services/chat_service.py`
- additive helpers under `backend/app/deepspace/services/`
- `backend/tests/unit/test_deepspace_chat_service.py`
- `backend/tests/unit/test_deepspace_runtime_transitions.py`

### E. Browser verification for budget visibility

What: Add a Playwright test, gated by the existing DeepSpace E2E environment
switch, that stubs a safe metrics-bearing stream and verifies the adaptive
budget text is rendered. It must not require production credentials or mutate
real data.

Why: Type/lint tests cannot prove that SSE metrics reach the visible composer.

Where:

- `frontend/e2e/deepspace-budget-metrics.spec.ts`
- `frontend/e2e/fixtures.ts` only if a reusable mock helper is required
- existing DeepSpace stream/thread components and tests

Safety and completion gates for A–E:

- No route, request schema, provider tool schema, approval policy, or tenant
  scope changes.
- No high-cardinality Prometheus labels and no sensitive trace data.
- Existing unknown-window behavior remains compatible.
- Existing DeepSpace/MCP unit tests, all `unit_no_db` tests, frontend unit
  tests, targeted lint, and the gated browser test pass.
- The replay harness must fail closed on malformed fixture data and must not
  call live providers or write to production storage.
- `backend/scripts/benchmark_deepspace_latency.py` must default to dry-run and
  reject non-local hosts unless an explicitly approved staging flag is passed.

## Follow-up implementation status

Completed safely:

- A: bounded workload-aware allocation for balanced, research, coding, and
  conversation-oriented turns; unknown context windows remain conservative.
- B: low-cardinality Prometheus counters, admin metrics summary fields,
  dashboard cards, and alerts for allocation spikes and canary mismatches.
- D: extracted workload classification and execution-batch planning seams from
  `stream_turn()` without changing the stream route or provider contract.
- E: gated Playwright coverage that stubs the SSE stream and verifies the
  adaptive budget values visible in the composer.
- Fixed the two DeepSpace frontend test harness failures by aligning the page
  test with the current explicit Notes workspace selection and wrapping chat
  history tests in the real `AuthProvider` with complete API mocks.
- Added a read-only, staging-gated latency-observation benchmark and a dry-run
  smoke test. It reports transport timing plus the existing tenant-scoped
  persisted turn p50/p95; it never creates a model turn.

Partially completed by design:

- C: checked-in replay fixtures are sanitized contract fixtures modeled on
  production-shaped flows. No real production trace was available in this
  workspace, so no claim is made that they came from production. The replay
  harness is ready to consume approved anonymized traces later and never calls
  live providers.
- Real production latency measurement remains environment-dependent. The
  local workspace has no approved staging token or production change window,
  so only the safe dry-run benchmark was executed here; no live traffic was
  generated.

Verification for this increment:

- New and affected backend unit/security tests pass.
- Entire backend `unit_no_db` suite passes.
- Targeted frontend DeepSpace tests pass.
- Targeted frontend ESLint has no errors; one pre-existing hook-dependency
  warning remains in `DeepSpaceChatClient.tsx`.
- Full frontend Vitest now passes after repairing the two requested DeepSpace
  test harness failures and two additional fixture gaps discovered by the full
  run. Existing React `act(...)` and jsdom navigation messages remain warnings
  from unrelated tests, not failures.

## Final verification harness implementation

### Offline trace replay harness

Add a strict replay loader and CLI. It accepts only versioned, sanitized event
traces, rejects prompt/content/token/credential-like fields, never imports
provider clients, never opens a network connection, and never writes to the
application database or Redis. The harness replays budget allocation, result
reference shape, execution-batch ordering, approval/cancellation lifecycle,
and terminal outcome invariants. Approved traces can be copied into the
fixture directory later without changing the runner.

Files:

- `backend/app/deepspace/services/replay_trace.py`
- `backend/scripts/replay_deepspace_trace.py`
- `backend/tests/unit/test_deepspace_replay.py`
- `backend/tests/fixtures/deepspace_replay/*.json`

### Controlled staging stream benchmark

Extend the observation script with an explicit `--stream` mode. The mode is
refused for non-local hosts unless `--allow-staging` and
`--write-staging-data` are both provided, requires an explicit synthetic
benchmark prompt, limits requests/concurrency, records only timing/status, and
never prints prompt/response/token data. It is not run here because no
approved staging credentials or change window are available. The default
remains dry-run/read-only summary observation.

Files:

- `backend/scripts/benchmark_deepspace_latency.py`
- `backend/tests/performance/test_deepspace_latency_benchmark.py`
- `backend/docs/deepspace/05-deepspace-operations-runbook.md`

Safety gates:

- No production host accepted by default.
- No trace fixture accepted with sensitive field names or live-provider
  directives.
- No stream benchmark without explicit staging and write opt-ins.
- Bounded requests, timeout, concurrency, and output fields.
- Local tests use only synthetic fixtures and no network.

Implementation status for this final harness increment:

- The fail-closed offline replay service, CLI, sanitized contract fixtures, and
  unit tests are implemented and verified locally.
- The latency script now supports both read-only operational-summary
  observation and an explicitly opt-in, bounded staging stream measurement.
- No approved anonymized production traces or staging credentials were present
  in this workspace, so real production replay and live staging measurement
  remain intentionally unexecuted external validation steps.
