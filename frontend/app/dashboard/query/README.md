# Query UI Surfaces

This query frontend renders both streamed and persisted assistant output through one Markdown-first
content path.

## Primary surfaces

- `message.content`: the canonical Markdown answer body rendered by `MarkdownRenderer`
- `message.blocks`: fallback table/chart/diagram payloads rendered only when the same content is not
  already present in Markdown
- `message.artifacts` and `message.files`: generated files/artifacts rendered by `ArtifactsPanel`
- `message.statusHistory`: lifecycle entries rendered by `StatusHistoryPanel`
- `message.trace`: analytical reasoning trace rendered by `ReasoningTrace`
- `message.followups`: follow-up suggestions rendered after completion

## Integration rules

- Reducer state in `_lib/query-thread-reducer.ts` is the source of truth for streamed query state.
- Markdown owns text, headings, lists, tables, math, images, code fences, and Mermaid fences.
- Structured output stays additive and must not duplicate content already rendered from Markdown.
- Explicit `chart` fences are promoted directly by `MarkdownRenderer`; there is no second streaming
  document AST or Markdown parser.
- Files/artifacts remain visible across streaming completion and persisted history replay.
- Status timeline entries are timestamped phase records with stable stage codes such as
  `context`, `retrieval`, `grounding`, `trace`, `synthesis`, and `followups`.
- `graph_json` stays on `GraphBlock`; Mermaid stays on the Mermaid renderer path.
- Retrieval depth is adaptive. The query UI no longer exposes a manual Top K slider; the
  backend chooses retrieval/rerank/answer breadth per query and reports the effective plan
  through status history and reasoning trace metadata.

## Backend contract

The backend persists and/or streams:

- `status_history`
- `files`
- `output`
- `blocks`
- `reasoning_trace`
- `follow_up_suggestions`

Frontend history replay and live streaming should render the same surfaces from those fields.

## Surface boundary

The Query surface is retrieval-first and owns only `/queries/*` and `/chats/*` query history. It must
not be used as a DeepSpace transport or renderer. DeepSpace owns its separate `/deepspace/chats/*`
API, provider-backed productivity stream, history repository, schemas, Markdown renderer, and note
workspace. Do not add `conversation_kind: "deepspace"` to a Query request; DeepSpace requests use
`{ message, conversation_id, thinking_enabled }` on `/deepspace/chats/stream`.

## DeepSpace Web Search

DeepSpace open chat supports an explicit Web toggle. When the toggle is enabled, the backend treats
web access as an explicit search command for that turn. It calls the configured web-search provider
before answering, then uses the returned results as external context for the open-chat response.

The first supported web-search provider is Tavily. Configure it from Settings -> Providers -> Web
with an API key and the default Tavily API URL `https://api.tavily.com`. Results are fetched
server-side, optionally reranked through the existing reranker provider, and injected into the
Open Chat prompt as bounded context. Raw provider secrets are never streamed or persisted.

Persisted assistant metadata may include a `web_search` object with:

- `enabled`: whether the user allowed web search for the turn
- `used`: whether a web provider was actually called
- `provider`: selected provider type, source, and request id when available
- `answer`: Tavily's synthesized answer summary when returned
- `results`: source titles, URLs, and scores used as context
- `usage`: provider usage metadata returned by Tavily
