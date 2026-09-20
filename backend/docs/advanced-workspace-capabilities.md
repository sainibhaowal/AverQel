# Advanced workspace capabilities

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
