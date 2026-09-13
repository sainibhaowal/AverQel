# Advanced workspace capabilities

This document is the production hand-off for the six optional DeepSpace
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

## 5. Scheduled and long-running work

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

## 6. MCP connections

1. The existing MCP marketplace, OAuth, encrypted credentials, tenant
   isolation, approval policy, discovery, and audit events remain the only
   connection framework.
2. Add connectors only as verified catalog entries requested by users. Do not
   add arbitrary remote servers or bypass approval/credential policy.
3. Connected MCP tools are merged into the same provider-neutral tool loop and
   therefore work independently of the selected model.

## 7. Validation and non-regression requirements

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
