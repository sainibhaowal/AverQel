# DeepSpace productivity task loop

DeepSpace uses a bounded, provider-facing tool loop for multi-step productivity work. It is separate from Query, terminal, file explorer, orchestration, proactive systems, and MCP.

## Available tools

- `todo_write` creates or replaces the task plan.
- `todo_read` reads the current conversation task plan.
- `todo_check` verifies completion, blockers, and evidence.
- `todo_mark` records a task status and evidence.
- `observe` inspects current note, task, Library, and active-response state without mutation.
- `analyze` evaluates the current task/workspace evidence and recommends the next safe action.
- `read`, `find`, `write`, `edit`, and `delete` are explicit-target workspace operations for note, Library, memory, chat, and tasks where supported.
- `write` can copy an already-persisted assistant response directly into a named Library file with `source='previous_assistant'`; it does not resend or regenerate the content.
- `web_search` searches through the configured server-side provider when current sources are required.
- `final` is accepted only after the required task list is complete or no task list exists.

The model never receives shell, terminal, file-system, or arbitrary cURL access through this loop. Thinking deltas are display-only; structured tool calls and tool results control execution. The DeepSpace tool contract is provider-independent: every configured chat provider receives the same productivity, web, URL/image, and explicitly attached MCP tools. The provider adapter translates that contract to the provider's native function-calling format (Google Gemini, Anthropic, OpenAI-compatible APIs, OpenCode Zen, and local OpenAI-compatible runtimes).

Provider and model support is still bounded by the upstream model's capabilities: a model must accept function/tool calling for autonomous tool execution. DeepSpace does not silently pretend a prose-only model called a tool; it keeps the tool stream visible and reports provider/model rejection as an explicit runtime error.

## Safety boundaries

Task rows are scoped by tenant, user, and DeepSpace conversation ID. The existing `agent_todos` table is reused, with dependencies and evidence stored in its JSON metadata. Note and Library writes are scoped to the active `deepspace` conversation. Reference saves resolve the source message server-side and return file evidence without copying the content through another model turn. Every loop is bounded by a maximum of 12 rounds, a maximum of 3 web searches, per-tool timeouts, one retry, cancellation checks, and duplicate-call detection.

The frontend receives `agent_status`, `tool_start`, `tool_delta`, `tool_result`, `tool_error`, and `observing` SSE events. Tool argument fragments are streamed as they arrive, so a busy operation remains visible instead of appearing hung.

## Self-hosted SearXNG

The Compose files include a private `searxng` service at `http://searxng:8080`. The API reaches it over the Compose network; it is not published to the host or Caddy. JSON search output is enabled in `backend/searxng/settings.yml`.

Set `SEARXNG_SECRET` to a random deployment secret. The local Compose fallback is intentionally marked for replacement in production. The provider applies server-side timeouts, rate limits, domain restrictions, result normalization, and SSRF protections. The model can request a search, but it cannot execute arbitrary HTTP or shell commands.

## Main implementation locations

- `app/deepspace/services/chat_service.py` - tool schemas, bounded loop, retries, cancellation, SSE deltas, citations, and final verification.
- `app/deepspace/services/task_loop.py` - tenant/user/conversation-scoped task and note storage.
- `app/providers/services/searxng_provider.py` - server-side SearXNG client and response normalization.
- `docker-compose.yml`, `docker-compose.prod.yml`, `searxng/settings.yml` - private SearXNG deployment.
- `../frontend/app/dashboard/deepspace/_lib/constants.ts` - user-facing tool status labels.
