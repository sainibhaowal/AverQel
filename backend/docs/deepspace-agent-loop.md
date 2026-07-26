# DeepSpace productivity task loop

DeepSpace uses a bounded, provider-facing tool loop for multi-step productivity work. It is separate from Query, terminal, file explorer, orchestration, proactive systems, and MCP.

## Available tools

- `todo_write` creates or replaces the task plan.
- `todo_read` reads the current conversation task plan.
- `todo_check` verifies completion, blockers, and evidence.
- `todo_mark` records a task status and evidence.
- `observe` inspects the active note and task state without mutation.
- `analyze` evaluates the current task evidence and selects the next task.
- `read` reads only the active DeepSpace note.
- `write` writes Markdown only to the active DeepSpace note.
- `web_search` searches through the configured server-side provider when current sources are required.
- `final` is accepted only after the required task list is complete or no task list exists.

The model never receives shell, terminal, file-system, arbitrary cURL, or MCP access through this loop. Thinking deltas are display-only; structured tool calls and tool results control execution.

## Safety boundaries

Task rows are scoped by tenant, user, and DeepSpace conversation ID. The existing `agent_todos` table is reused, with dependencies and evidence stored in its JSON metadata. Note writes are scoped to the active `deepspace` conversation and rendered through a small escaped Markdown subset. Every loop is bounded by a maximum of 12 rounds, a maximum of 3 web searches, per-tool timeouts, one retry, cancellation checks, and duplicate-call detection.

The frontend receives `agent_status`, `tool_start`, `tool_delta`, `tool_result`, `tool_error`, and `observing` SSE events. Tool argument fragments are streamed as they arrive, so a busy operation remains visible instead of appearing hung.

## Self-hosted SearXNG

The Compose files include a private `searxng` service at `http://searxng:8080`. The API reaches it over the Compose network; it is not published to the host or Caddy. JSON search output is enabled in `backend/searxng/settings.yml`.

Set `SEARXNG_SECRET` to a random deployment secret. The local Compose fallback is intentionally marked for replacement in production. The provider applies server-side timeouts, rate limits, domain restrictions, result normalization, and SSRF protections. The model can request a search, but it cannot execute arbitrary HTTP or shell commands.

## Main implementation locations

- `app/deepspace/services/chat_service.py` — tool schemas, bounded loop, retries, cancellation, SSE deltas, citations, and final verification.
- `app/deepspace/services/task_loop.py` — tenant/user/conversation-scoped task and note storage.
- `app/providers/services/searxng_provider.py` — server-side SearXNG client and response normalization.
- `docker-compose.yml`, `docker-compose.prod.yml`, `searxng/settings.yml` — private SearXNG deployment.
- `../frontend/app/dashboard/deepspace/_lib/constants.ts` — user-facing tool status labels.
