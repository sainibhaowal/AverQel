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

## Citation previews

Opening a citation uses the authenticated Documents API. PDFs and Office formats supported by the
server renderer use the rendered page endpoint, which invokes LibreOffice for supported Office
files. The viewer also offers the format-aware preview for extracted text, tables, and browser
media. CSV citations use the bounded `/documents/{document_id}/csv-page` endpoint so large tables
load a page of rows at a time instead of transferring the complete file into the browser. When page
rendering fails, the viewer shows an error and keeps any available format preview usable.

## Backend contract

The backend persists and/or streams:

- `status_history`
- `files`
- `output`
- `blocks`
- `reasoning_trace`
- `follow_up_suggestions`

Frontend history replay and live streaming should render the same surfaces from those fields.

## Composer model, files, and queue

- The model menu searches available chat models, groups matches by provider, and shows each
  provider's local brand mark. Provider groups are keyboard-operable accordion buttons; opening one
  closes the previous group. Selecting a model continues to update the existing chat assignment.
- The paperclip uploads each selected file through the authenticated Documents Hub upload endpoint.
  Up to three files upload at a time. The composer shows waiting, uploading, indexing, ready, or
  failed status for each file and waits for the persisted document and searchable chunks to reach
  the indexed state before allowing the query to send. CSV and TSV attachments also wait for their
  separate Grounded Query table index to reach Ready. Upload tracking stays active while navigating
  between pages in the same open app window or browser tab. The Hub shows the in-progress Query upload there, then
  replaces that temporary row with the saved document and its normal live indexing status when the
  server accepts it. The temporary row is not restored after a full page reload. Upload validation,
  malware scanning, quarantine, extraction, chunking, and embeddings remain owned by the existing
  Documents Hub pipeline.
- A query can attach up to 10 indexed files. The stream request carries their document IDs in
  `filters.attached_document_ids`. The API validates those IDs against the authenticated user's
  accessible, non-quarantined, indexed documents and includes them alongside the normal collection
  or document scope. A file that is inaccessible, quarantined, failed, or not yet indexed cannot be
  used as an attachment; a direct API request with an unindexed attachment is rejected.
- While a query is streaming, submitting another prompt adds it to the page's in-memory queue.
  Queue items keep the query text, attachment IDs, and current retrieval options, and are sent one
  at a time through the existing `/queries/stream` endpoint. The queue holds up to 20 pending
  prompts. Users can pause or resume the queue, remove individual items, clear it, or stop the
  active query. A failed stream pauses the queue and keeps that prompt at the front for an
  explicit retry before later prompts continue. The queue is local to the current browser page
  session; queued prompts are not durable and are cleared when the user starts or switches
  conversations.
- Removing an attachment from the composer only detaches it from that query. The uploaded source
  remains in Documents Hub and follows its existing retention and deletion controls.

## Grounded Query tables

- The composer checks the selected file's SHA-256 against documents already accessible to the signed-in
  user. If a safe, matching Documents Hub file exists, it attaches that document ID and skips a second
  storage upload. The add-existing picker also attaches indexed Documents Hub files directly. Both
  paths preserve the normal tenant and per-user document access checks.
- CSV and TSV tables are accepted up to **25 MiB**, **1,000,000 data rows**, and **256 columns**.
  Indexing runs in the separate `grounded_query_datasets` worker after the existing Documents Hub
  scan and indexing complete. The composer shows the table stage and progress. Invalid or over-limit
  files fail visibly; indexing never silently drops rows. Retrying repeats the validation from the
  stored source file.
- When a question asks for exact table work, such as filtering, sorting, counting, summing, averaging,
  or grouping, the model prepares a structured plan using only the user request and table schema.
  Backend validation then runs the supported operation against the complete indexed table. The
  answer combines the exact result with retrieved source context; it does not send the full table to
  the planning model. Each calculation uses every matching row. Displayed row results are capped at
  100 per answer.
- Table citations identify the source file, show the matching-row count, and list up to 20 source-row
  examples. Source row 1 is the header. Opening a citation loads a 100-row window and offers direct
  row jumps; requests are capped at 200 rows and 50 columns. Long cell previews are shortened with
  an explicit notice so the full dataset stays out of the browser response.

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
