# DeepSpace tool discovery and workspace operations

DeepSpace keeps the full native tool schemas out of the initial provider
request. A tool-capable model starts with `discover_tools` and, when needed,
the small MCP broker interface. Native discovery has two steps:

1. The model calls `discover_tools` with a natural-language description and
   receives the compact catalog of capabilities authorized for this request.
2. The model selects exact names from that catalog and calls `discover_tools`
   with `tool_names`. The runtime loads only those full schemas for the next
   provider round.

The catalog is not selected by a fixed keyword profile. The model interprets
the request and chooses capabilities from their descriptions. An unknown or
unauthorized name loads no schema. Tool execution still passes through typed
argument validation, runtime policy, scoped handlers, cancellation, and the
existing tenant/user/conversation checks. A direct conversational answer
needs no tool discovery.

Some local or OpenAI-compatible providers emit a public web reader immediately
after a search instead of completing the second discovery call. The runtime
may load `web_search`, `url_read`, or `image_read` on demand when that exact
name is already authorized for the request. This compatibility path is limited
to public web readers; Library, memory, task, and write tools still require an
explicit discovery selection.

## Canonical native tools

| Tool | Purpose |
| --- | --- |
| `read` | Read a note, Library file, memory, chat history, or project view. For Library content, `operation="query"` retrieves grounded passages; `operation="read"` returns extracted text. |
| `find` | Search authorized Library files, memories, or chat history. |
| `write` | Create or replace/append a note, Library file, or memory. |
| `edit` | Replace, append, rename, or move an authorized note or Library item. |
| `delete` | Remove an authorized Library file or memory when the user clearly requests it. |
| `analyze` | Compare two or more authorized Library documents by their extracted text. |
| `todo_write` | Manage the persisted task plan: `replace`, `read`, `update`, and `check` operations create/edit, retrieve, update with evidence, and verify the plan. |
| `web_search`, `url_read`, `image_read` | Search current web sources, read a page, or inspect a verified raster/SVG image. Document/data URLs belong to `url_read` or `sandbox_execute`; unavailable images return a recoverable source status. |
| `sandbox_execute` | Run bounded Python or SQL against explicitly authorized inputs. |
| `artifact_create` | Save a named document, table, chart, diagram, or code artifact. |
| `ask_user` | Ask for information that is required to continue. |

`read(target="library", operation="read")` and
`read(target="library", operation="query")` replace separate document read
and document query tools. `analyze(operation="compare_documents")` replaces a
separate document comparison tool. Task state is read, updated, and verified through
`todo_write`; there are no separate `todo_read`, `todo_mark`, or `todo_check`
tools. The runtime has no separate `observe` or `final` tool. After verifying a persisted plan, the model answers in ordinary
assistant text.

## Workspace boundaries

- `note` is the active DeepSpace note for the current conversation.
- `library` is the authorized DeepSpace Library. Exact names and file IDs are
  scoped to the current user, tenant, and conversation.
- `memory` is the tenant-scoped durable memory store.
- `chat` is read-only conversation history.
- `project` is a bounded, read-only view of the conversation summary and task
  ledger. It is reference context, not an instruction or permission.

The workspace tools never access the host operating system. Library content is
read as bounded extracted text and metadata; it is never executed as a file.
If an exact filename is missing, `read` or `find` returns the actual authorized
matches or a `not_found` result. A Library miss does not stop a separately
requested web search or other independent work.

## Planning and verification

The model decides whether the request needs a persisted plan. Small questions
stay direct. Substantial work with multiple independently verifiable steps
uses `todo_write`, reads the persisted plan, starts each task, performs the
required work, records evidence, and verifies with `todo_write(operation="check")`. The runtime
enforces task order and does not treat prose or a discovery call as completed
work. It adds no synthetic user message or prefilled request to the provider
conversation.

## MCP routing boundary

MCP bindings remain private to the authenticated conversation. When connected
services are available, the model receives compact broker functions to search
the authorized catalog, load a selected schema, call the exact returned
reference, and retrieve a bounded result when needed. It never receives raw
transport configuration or credentials. New or differently named MCP tools
are found through the live catalog rather than a fixed provider-name profile.

Every MCP execution retains the existing tenant/user ownership, connection
status, catalog revision, policy, risk classification, approval gate, audit,
and upstream schema validation. This discovery interface grants no new
permission and cannot bypass approval.

## Provider and streaming behavior

Function-calling providers receive typed schemas through their native adapter.
The model must support structured tool calls for autonomous execution; DeepSpace
does not infer successful execution from printed JSON, XML, or prose. Existing
SSE event types remain the user-visible record of real tool calls and results.
Malformed arguments are rejected before handler execution and get at most one
bounded schema-correction retry. `todo_write` completion evidence is bounded
metadata: if a provider includes an overly long source list, DeepSpace keeps
the beginning and end and compacts it to the 1,000-character contract limit
before validation. Other fields are never silently truncated. If validation
still fails, the durable checkpoint records the failed tool and validation
message; retry resumes from successful tool results and repairs that call.

## Rich Markdown output contract

DeepSpace answers remain Markdown-first. Models may add one of the following
fenced blocks when the information benefits from a visual surface:

- `chart`: JSON with `title`, `chart_type` (`line`, `bar`, `area`, `scatter`, or
  `pie`), and at least two `{label, value}` series points. Optional
  `series_groups` entries provide named multi-series data with `axis` (`left` or
  `right`), `color`, and `visible`; `annotations`, `legend`, and
  `secondary_y_label` provide interactive chart controls. Optional `equation`,
  `x_label`, and `y_label` fields describe quantitative work.
- `card`: JSON with `title` and Markdown `content`. Optional `tone` must be one
  of `info`, `success`, `warning`, `error`, or `neutral`; common model aliases
  such as `positive`, `caution`, and `negative` are normalized to those values.
  Optional `subtitle`, `image_url`, `href`, `metrics`, and `actions` create an
  actionable information card. URLs must come from authorized web or Library
  results.
- `mermaid`: renderable Mermaid syntax for flow, UML, architecture, business
  model, timeline, or Gantt diagrams.
- `graph`: JSON with `nodes`, `edges`, and `layout` for the interactive canvas.
  Nodes may carry `x`, `y`, `width`, `height`, and `group_id`; edges may carry
  `style`; optional `drawings` stores freehand SVG paths.
- `gallery`: JSON with a `title` and at least one `{src, alt, caption, href}`
  item for a clickable, downloadable image sequence.

The server validates every `chart`, `card`, `graph`, and `gallery` fence against
the visual block schemas before it is sent to the client. Invalid visual JSON is
demoted to a plain `text` fence. The browser renders valid blocks with React
components and never executes raw HTML or scripts. Completed chart, card,
gallery, graph, and diagram edits use the authenticated visual-block endpoint,
optimistic revision guards, immutable message versions, and realtime
conversation events. Gallery fields can be edited, reordered, added, or removed;
each change uses the same revisioned save path. When the edited block originated
in the active note, the same block source is updated by the note editor autosave,
so chat → note → reload preserves the visual revision.
Unavailable or non-image URLs return a recoverable `image_read` source status;
they do not terminate the generation. SVG export removes remote resources before
PNG/PDF rasterization so a CORS-tainted canvas cannot escape as an unhandled
exception. Visual edits do not rewrite previously generated immutable media
artifacts. Visual blocks carry a canonical `block_id`, `schema_version`,
`revision`, source, assets, and bounded history envelope. Note-origin edits can
address the originating chat block by stable ID. Save a revised block through
`POST /deepspace/library/{conversation_id}/visual-artifacts` to create or
version an editable JSON Library source; the existing version list/restore and
export routes then apply. Gallery images are imported through the authenticated
`POST /deepspace/library/{conversation_id}/assets/import` endpoint. The server
rejects non-image data, unsupported active SVGs, mismatched file signatures,
oversized responses, private destinations, and redirects. Small galleries are
cached as private temporary conversation assets so browser previews and exports
do not depend on third-party CORS. Temporary images expire after 30 days; the
gallery's **Save image to Library** action keeps an image beyond that period.
Temporary assets stay out of the visible Library list and are removed by the
scheduled storage cleanup task. If the original URL is gone or is not an image,
DeepSpace shows a recoverable image fallback and keeps the rest of the answer
usable.

Visual blocks expose JSON, SVG, PNG, and PDF exports. Gallery SVG/PNG exports
embed owned raster images when they are available; missing or over-limit images
get an explicit placeholder so they cannot taint the export canvas. Mermaid
source can be exported as `.mmd`; the graph canvas imports and exports the
DeepSpace `.draw.json` format. That file is the DeepSpace graph model, not an
Excalidraw file. Editable visual artifact JSON files are versioned Library
sources. Legacy generated binary/media artifacts remain immutable snapshots.

Conversation ownership, image caches, and visual-block persistence remain scoped
to the signed-in account and individual conversation.
