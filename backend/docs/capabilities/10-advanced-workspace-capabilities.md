# 10. Advanced workspace capabilities

This document is the production hand-off for DeepSpace's optional and advanced
capabilities. The numbered sections are intentionally explicit about what is
available, what is gated, and which security boundary protects each feature.

## 1. Sandboxed Python, SQL, and data work

1. `POST /api/v1/deepspace/sandbox/execute` accepts bounded `python` or
   read-only `sql` requests and requires the existing `queries:run`
   permission.
2. The `sandbox_execute` DeepSpace tool uses the same endpoint and is exposed
   to every provider through AverQel's backend tool registry; the model never
   decides whether host execution is allowed.
3. API and worker containers never execute submitted code. They call the
   `sandbox-executor` sidecar only when `AKS_DEEPSPACE_SANDBOX_ENABLED=true`.
4. Enable it with `docker compose --profile sandbox-execution up -d
   sandbox-executor`, a high-entropy `AKS_DEEPSPACE_SANDBOX_TOKEN`, and the
   matching API/worker environment variables.
5. The executor has no public port, no host mount, an internal-only network,
   read-only root filesystem, dropped capabilities, `no-new-privileges`, PID,
   memory, CPU, request-size, output-size, and timeout limits.
6. Python imports that expose host/network primitives are rejected before
   execution. SQL accepts one `SELECT`/`WITH` statement over supplied JSON
   tables; mutation, attachment, pragma, and multi-statement SQL are rejected.
   The executor image includes `pandas`, `openpyxl`, and `matplotlib` for
   approved data analysis and chart preparation; generated files remain in
   the ephemeral sandbox unless explicitly returned by a future artifact job.
7. A production deployment should additionally run this image under gVisor,
   Kata, or Firecracker and apply an egress-deny policy at the cluster level.

## 2. Rich document intelligence

1. Existing tenant-scoped Library storage and extractors remain the source of
   truth for PDF, DOCX, PPTX, XLSX, CSV, OCR, tables, and text.
2. `document_read` returns bounded extracted text, document metadata, and a
   file citation identifier after the normal conversation/user/tenant check.
3. `document_compare` reads two authorized files and returns a bounded unified
   diff with both file identifiers; it cannot cross conversations or tenants.
4. `document_query` and `POST /api/v1/deepspace/documents/query` return
   bounded matching passages with stable `file:{id}#L{line}` citations.
5. The existing `read`, `find`, Library preview, chunking, and citation
   pipelines remain unchanged and continue to support ordinary chat turns.

## 3. Controlled browser automation

1. `backend/app/deepspace/services/browser_reader.py` is a read-only adapter
   for JavaScript-rendered public pages; it is not a general browser with
   cookies, credentials, downloads, or side effects.
2. The `research-browser` compose profile isolates Chromium behind Squid and
   an internal network. SSRF validation, strict timeouts, response-size caps,
   and bearer authentication are mandatory.
3. Keep the profile disabled unless the renderer image and egress policy have
   been smoke-tested in the target environment. Failed renders are reported
   as unavailable/snippet-only evidence rather than verified content.
4. The DeepSpace research route exposes `web_search` and `url_read` together;
   the model reads a selected HTTPS result before summarizing. Static reading
   falls back to the isolated browser adapter only for an empty JavaScript
   shell when the renderer is enabled.

## 4. Artifacts and exports

1. Existing authenticated PDF, DOCX, Markdown, Library, spreadsheet, and
   media-artifact routes remain the durable artifact boundary.
2. `POST/GET /api/v1/deepspace/artifacts/jobs` creates and observes durable
   artifact jobs. A Celery worker materializes the result through the
   tenant-scoped Library boundary.
3. Assistant-created reports should be written to the tenant-scoped Library
   through `write(target="library")`; downloads still require authenticated
   ownership checks.
4. Provider-generated media continues to use the immutable object-storage
   record and range-safe artifact delivery route.
5. Conversation exports now include PDF, DOCX, Markdown, and editable PPTX
   (`GET /api/v1/deepspace/export/{conversation_id}?format=pptx`).
6. Rendered chat Mermaid diagrams have client-side actions to copy their Mermaid
   source and export `.mmd`, SVG, PNG, or PDF. Markdown and structured tables
   can be copied as TSV or exported as CSV/XLSX; reasoning traces can be copied
   or exported as JSON. These actions operate only on browser-rendered content:
   they add no API route, database record, background job, credential access,
   or cross-tenant data path.
7. Diagram SVG export removes executable and external-reference markup before
   download. PNG/PDF exports are derived from that sanitized SVG locally. An
   invalid or still-rendering Mermaid diagram keeps visual exports disabled,
   while source copy and `.mmd` export remain available.

## 5. DeepSpace reasoning effort

1. The DeepSpace composer exposes a dedicated Thinking selector with Off, Low,
   Medium, High, and—when a model advertises them—Very High and Extreme High.
   The selected value is sent with direct, queued, regenerate, and
   edit-and-regenerate requests.
2. Provider model metadata remains authoritative. DeepSpace resolves
   capabilities from live provider discovery, persisted model metadata, and a
   verified family registry, in that order. A narrower native capability is
   mapped to the nearest supported normalized level; unsupported models do not
   receive a forced reasoning payload.
3. Provider adapters continue to translate the normalized effort into their
   native controls. Existing boolean `thinking_enabled` clients remain
   compatible.
4. Queued turns persist the selected effort in the tenant-scoped
   `deepspace_queued_turns.reasoning_effort` column. Migration:
   `20260919_0001_deepspace_reasoning_effort.py`.
5. Native adapter mappings are capability-gated: Groq/OpenAI-compatible
   models use `reasoning_effort`; DeepSeek uses its `thinking` plus mapped
   effort values; Gemini uses `thinkingLevel` for Gemini 3 and
   `thinkingBudget` for Gemini 2.5; Anthropic uses effort-scaled thinking
   budgets for legacy extended-thinking models; LM Studio uses its native
   `reasoning` setting while retaining local-model compatibility controls.
   Unknown/future model metadata is never assumed to support a level.

## 6. Context budget meter

1. The composer displays an estimated request-context budget: serialized input
   plus streamed or completed output, divided by the selected model's verified
   context window. The estimate is explicitly labelled because providers do
   not share a universal tokenizer.
2. Context-window resolution uses live model discovery first, then persisted
   provider metadata, then a verified official model-family fallback. Unknown
   models remain `Unavailable`; the UI never invents a denominator.
3. Diagnostics show request context, reserved output, safe remaining context,
   visible conversation counts, compaction state, and optional provider prompt
   cache eligibility. Prompt caching is provider-specific and is not the same
   as the context-window cache.
4. DeepSeek `deepseek-flash` and `deepseek-v4-pro` use their documented
   1,048,576-token context window. Context limits travel in stream metadata
   and final metrics so the meter works during and after a response.

## 7. Voice input and output

1. LiveKit provides the authenticated realtime media transport. The browser
   obtains a short-lived room token from `GET /api/v1/voice/token`; API keys,
   secrets, STT models, and TTS models never enter the browser.
2. The `voice-agent` subscribes to enabled microphone audio, performs local
   Whisper transcription, and sends partial/final dictation updates to the
   composer. The user must grant browser microphone permission.
3. When TTS is enabled, the completed visible assistant answer is sent to the
   room and synthesized locally with Kokoro. Internal thinking, tool payloads,
   and credentials are not spoken.
4. The Compose stack runs `livekit` and `voice-agent` with dedicated health
   checks and model mounts. Production deployments require HTTPS/WSS and a
   TURN configuration appropriate to the deployment network.

## 8. Scheduled and long-running work

1. `deepspace_schedules` stores user/tenant/conversation ownership, prompt,
   interval, status, next run, last run, and the durable request id.
2. REST routes are `POST/GET /api/v1/deepspace/schedules`,
   `PATCH/DELETE /api/v1/deepspace/schedules/{schedule_id}`. All routes use
   `queries:run` and enforce the authenticated tenant and user.
3. `GET /api/v1/deepspace/schedules/{schedule_id}/runs` exposes durable
   queued/running/completed/failed/cancelled run history.
4. Celery Beat runs `deepspace.dispatch_schedules` every minute. It claims due
   rows with `SKIP LOCKED`, advances the next run before enqueueing, and then
   uses the normal `deepspace.run` path so SSE reconnect, cancellation, audit,
   and provider selection are not duplicated.
5. The migrations are `20260913_0001_deepspace_schedules.py`,
   `20260913_0003_schedule_runs.py`, and the artifact job migration
   `20260913_0002_artifact_jobs.py`. Apply migrations
   before enabling the scheduler worker/beat process.
6. Pausing or deleting a schedule is idempotent. Notification delivery is
   intentionally left to the existing event/SSE and connector policy rather
   than sending unsolicited external messages.

## 9. MCP connections

1. The existing MCP marketplace, OAuth, encrypted credentials, tenant
   isolation, approval policy, discovery, and audit events remain the only
   connection framework.
2. Add connectors only as verified catalog entries requested by users. Do not
   add arbitrary remote servers or bypass approval/credential policy.
3. Connected MCP tools are merged into the same provider-neutral tool loop and
   therefore work independently of the selected model.

## 10. Validation and non-regression requirements

1. Run backend formatting/lint/type checks from `backend/.venv` (the project
   pins the tools; a global formatter is not required).
2. Run sandbox policy/client tests, DeepSpace tool-loop tests, URL-security and
   browser adapter tests, schedule API/migration tests, and the existing full
   backend/frontend suites.
3. Verify that no route accepts a tenant id from the request body, no executor
   request follows redirects, no user code runs in API/worker containers, and
   no artifact or document response bypasses authentication.
4. Existing chats, provider integrations, encrypted secrets, RLS/tenant
   checks, storage, memory, SSE recovery, exports, and MCP approvals must
   remain behavior-compatible.

## 11. DeepSpace provider prompt baseline

1. Provider APIs are stateless, so DeepSpace still sends a self-contained
   request on every provider turn. The stable policy is deliberately retained
   as the first request prefix; it is not removed from generic providers.
2. The prefix is versioned by `DEEPSPACE_PROMPT_BASELINE_VERSION` and its
   policy/boundary digest. Anthropic and Google requests reuse one stable,
   conversation-scoped cache identity across internal agent rounds, allowing
   their native prompt-cache mechanisms to reuse unchanged system context.
3. Changing the baseline policy or current-turn boundary changes the digest and
   safely starts a new provider cache generation. This prevents stale hidden
   instructions from being reused after a policy change.
4. Generic OpenAI-compatible providers receive no unsupported cache fields and
   retain the existing full-request fallback. This is required for correctness
   because those APIs do not provide a universal server-side prefix-cache
   contract.
5. Stream metrics and assistant metadata expose the baseline version and
   digest for diagnostics. They do not expose policy text, credentials, tenant
   data, or hidden reasoning.

## 12. Dynamic instruction hygiene

1. Temporary DeepSpace guidance is keyed by purpose rather than appended as
   anonymous system history. Current keys cover greeting guards, MCP
   attachment context, reasoning-only recovery, tool-output recovery, task
   lifecycle recovery, clarification recovery, invalid-tool-argument recovery,
   and context-compaction notices.
2. Replacing an instruction with the same key removes its stale predecessor
   before the next provider turn. A retry therefore cannot accumulate multiple
   contradictory recovery messages or repeatedly grow the hidden prompt.
3. Internal instruction keys are removed at the provider boundary. They are
   never exposed to models, persisted as user-visible content, returned by
   history APIs, or included in frontend activity text.
4. Tool calls, tool results, user messages, approvals, and durable task events
   remain chronological messages. Only transient instruction guidance is
   replaceable; this preserves provider tool-call protocol correctness and
   durable audit behavior.

## 13. Compact MCP model boundary

1. DeepSpace exposes one stable `mcp_broker` function schema to the model,
   with `search`, `schema`, and `call` operations. The previous three-function
   broker definitions remain available internally for compatibility and tests,
   but are not placed in the provider request.
2. The broker resolves operation requests to the existing private catalogue,
   exact conversation-scoped tool references, input-schema validation, MCP
   policy, approval gates, encrypted connection handling, tenant checks, audit
   events, and bounded result projection.
3. The model never receives the complete MCP catalogue, upstream server names
   outside the selected routing scope, transport credentials, or unrestricted
   upstream schemas. The compact schema is stable across provider rounds and
   is eligible for the existing provider prompt-cache prefix.
4. A broker call cannot execute a guessed raw tool name: execution still
   requires a server-issued `tool_ref` resolved against the current scoped
   bindings.

## 14. MCP result projection

1. Successful remote MCP results are bounded, stored for a short period in a
   tenant/user/conversation-scoped Redis record, and replaced in model history
   by a compact preview plus an opaque `result_ref`.
2. The model can request more only through `mcp_broker` with
   `operation: "result"` and the returned reference. References expire and
   cannot be used across tenants, users, or conversations.
3. Credentials, raw transport responses, and unrestricted result payloads are
   never placed in conversation history. The existing MCP call/result budgets,
   policy checks, approvals, audit events, and server-side bounds remain in
   force.
4. This keeps intermediate data outside model context while preserving an
   explicit, auditable retrieval path when the answer genuinely requires more
   detail.

## 15. Context epochs and live compaction

1. DeepSpace maintains a tenant/user/conversation/provider/model-scoped
   context epoch in Redis. Each epoch records the baseline digest and named
   source digests for MCP attachments, selected tools, lifecycle state, and
   the current policy boundary.
2. A source change starts a new epoch. Context compaction also starts a new
   epoch after history is safely reduced to fit the verified model window.
3. Compaction is request-local and conservative: the complete transcript stays
   persisted, only the provider projection is reduced, and the request is
   rebuilt with the stable policy baseline plus the newest safe history.
4. Stream metrics expose the epoch, transition reason, source updates, context
   usage, safe remaining budget, and compaction state. The composer shows a
   small live epoch/compaction status inside Request diagnostics without
   exposing hidden instructions or private data.
5. Redis loss never blocks a request or changes authorization. The system
   falls back to an ephemeral epoch while retaining the existing context-fit
   and safety behavior.

## 16. Provider prompt-cache coordination

1. DeepSpace normalizes model-visible tool definitions by name before every
   provider request, preventing semantically identical rounds from producing
   different cache prefixes due only to ordering.
2. Each request carries a versioned baseline digest and stable cache-prefix
   digest. Anthropic and Google receive only their supported native cache
   controls; generic OpenAI-compatible providers receive no unsupported cache
   fields.
3. Diagnostics distinguish `native_requested`, `unsupported`, `disabled`, and
   `unknown`. DeepSpace never claims a cache hit when the provider does not
   expose hit telemetry.
4. Cache identity includes tenant, user, conversation, model, and baseline
   version. Policy changes therefore invalidate the prefix safely, while
   unrelated conversations cannot share cache identity.

## 17. Token-category diagnostics

1. DeepSpace reports separate serialized-request estimates for system context,
   tool schemas, and tool results, alongside visible input/output totals.
2. `uncachedInputTokens` currently represents the full local request estimate
   until a provider returns authoritative cache usage. `cachedInputTokens`
   remains `null` when the provider does not report cache reads.
3. Every category payload includes `tokenCategorySource`, so the UI never
   presents a local estimate as provider-billed exact usage.
4. The shared provider usage normalizer maps OpenAI-compatible/OpenResponses,
   Anthropic, and Gemini usage fields into `providerUsage`, including input,
   output, cache-read, and cache-write values where the provider reports them.
   Raw provider usage remains intact for compatibility. Providers that do not
   expose cache telemetry are explicitly reported as `unavailable`, never
   guessed as a cache hit.
5. Streaming adapters emit terminal usage events for OpenAI-compatible,
   Anthropic, and Gemini responses. The composer displays the authoritative
   provider values separately from local category estimates.

## 18. DeepSpace monitoring coverage

Prometheus counters are emitted from the real request path, not from UI
estimates or test-only code:

- `aks_deepspace_cache_usage_total`: provider-reported cache reads/writes.
- `aks_deepspace_context_compactions_total`: successful context-fit compactions.
- `aks_deepspace_context_overflow_prevented_total`: requests protected by
  compaction before exceeding the selected context window.
- `aks_deepspace_mcp_result_references_total`: bounded MCP results stored
  server-side behind a reference.

The rules in `backend/monitoring/prometheus/deepspace-alerts.yml` cover
compaction pressure, overflow prevention, cache telemetry absence, and MCP
reference spikes. Provider, tenant, user, conversation, tool, and result
content are intentionally excluded from metric labels to prevent sensitive
cardinality and data leakage.
