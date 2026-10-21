# AverQel web workspace

The `frontend/` package is the Next.js web client for AverQel. It runs behind
the AverQel API in production and is also used by the Electron desktop client.

## Getting Started

Use Node.js 22 (the production Docker image uses Node 22) and pnpm 10. The
workspace declaration in `frontend/pnpm-workspace.yaml` is required so the
checked-in Vitest 3 toolchain is installed instead of falling back to an
incompatible temporary Vitest version. Run the following frontend commands
from `frontend/`, or prefix them with `pnpm --dir frontend` from the repository
root.

```bash
corepack enable
corepack prepare pnpm@10.28.2 --activate
pnpm install --frozen-lockfile
pnpm test
```

Start the web client directly:

```bash
pnpm dev
```

From the repository root, the normal desktop development command starts the
frontend and Electron together:

```bash
pnpm electron dev
```

The frontend development server listens on `http://127.0.0.1:1030`.

Open [http://127.0.0.1:1030](http://127.0.0.1:1030) with your browser to see the result.

## Tavily Web Search Provider

DeepSpace can use Tavily for opt-in web search. Add a Tavily connection from
`Dashboard -> Settings -> Providers -> Web`, keep the base URL as `https://api.tavily.com`, and
store the Tavily API key through the provider form. The key is sent to the backend provider API and
stored through the existing encrypted provider-secret flow.

The DeepSpace composer exposes a Web toggle. When enabled, the backend searches through the
configured Tavily provider for that turn, then injects bounded Tavily results into the LLM context.

## Remote MCP Marketplace

AverQel's MCP Marketplace browses Composio's live app and tool catalog. Each AverQel account supplies
its own Composio project API key under Dashboard → Providers → MCP; AverQel encrypts and scopes that
key to the account and never returns it to the browser. The running backend decrypts it when it
calls Composio, so the key is not end-to-end encrypted from the server. The current Marketplace does
not list AverQel's former bundled Google, GitHub, Notion, and Slack cards; existing connection
records are retained.

The current connection flow is: user adds their Composio project key → browses the live catalog →
inspects an app and its tools → connects the selected app → completes its hosted authorization
when needed → uses the account-owned connection in DeepSpace, subject to tool policy and approval.

The deployment must configure the canonical public HTTPS origin for OAuth callbacks; local
development may use an HTTP localhost origin. Users do not configure a shared AverQel callback
verifier. Composio and the connected app handle authorization; each AverQel account must authorize
its own external app account. A catalog listing does not guarantee that an app is enabled for a
specific Composio project or will accept a requested action.

MCP connections are tenant- and user-scoped. Connected accounts are automatically available across
the owner's DeepSpace conversations. Tool access is checked through connection ownership,
current tool definitions, the saved connection policy, and the action approval rules. Writes,
deletions, and external messages require approval before execution; Always allow cannot bypass that
side-effect approval check. Disconnecting or removing a key clears local session state but does not
necessarily revoke authorization held by Composio or the external app. See the
[Composio hosted MCP guide](../backend/docs/capabilities/mcp/03-composio-hosted-mcp.md) for setup,
privacy, API, and troubleshooting details.

## Request and service reliability

The browser client bounds ordinary API requests at 10 seconds, authentication requests at 5 seconds,
and streaming requests at 120 seconds. A stalled request is aborted and surfaced as an error instead
of leaving a page action pending forever. Logout clears the local session immediately and reports a
server-side logout failure without blocking the user.

DeepSpace loads independent panels independently. A slow conversation-history, vitals, workspace, or
runtime request shows a visible warning and a Retry action while the rest of the workspace remains
usable. Normal agent runtime selection uses verified or cached provider metadata; live provider model
discovery belongs to provider-management refresh flows so an unavailable provider catalog cannot hold
the API request loop.

### DeepSpace live activity timeline

DeepSpace renders safe streamed activity in order: actual function-tool calls,
their streamed arguments and results, approval/input requests, task-plan and
verification events, and genuine errors. Raw provider reasoning remains
private backend state; it is not sent through SSE or persisted in assistant
metadata. Fixed backend status prose is not rendered as an agent step.
Function arguments are shown incrementally when a provider sends them. A tool
that only returns a final response is shown as running immediately and
completed when that real result arrives; the UI does not fabricate progress.

The model chooses whether a request needs a direct answer, workspace inspection, research, a connected
service, a clarification, or a task plan. It creates a plan with `todo_write` only when a multi-step,
agent-owned outcome benefits from one. Once a real plan exists, DeepSpace enforces its verified lifecycle:
`todo_write(operation="read")`, `todo_write(operation="update", status="in_progress")`, appropriate
work tools, `todo_write(operation="update", evidence=...)`, and `todo_write(operation="check")`.
`analyze` remains an optional real inspection tool, chosen when
the model needs workspace or evidence state. The visible task-progress card is derived from actual todo
tool results; it is not a synthetic status. A task may be completed only with evidence and after its
dependencies are complete.
The browser keeps the detailed local sequence during the automatic post-stream history refresh, so a
completed answer does not collapse the visible timeline into one combined thinking block.

An in-flight turn is durable: navigating away or refreshing reloads its saved
assistant message and reconnects with the same request ID. This is a replay
attachment, not a second model run, so completed timeline entries, tool state,
checkpoints, and the final answer remain in their original turn order.

The composer selects the enabled chat assignment when one exists. If it does
not, it selects the enabled provider's `default_chat_model`; discovered model
metadata takes precedence over a provider fallback. This makes the context
meter available immediately without requiring the user to reselect the model.

When an agent uses the DeepSpace `write` tool, the note panel also renders the real streamed Markdown
arguments as an in-editor **AverQel is writing** preview. The preview is not persisted token by token:
only the validated, tenant-scoped write-tool result replaces or appends the durable note. If a stream
fails, the draft remains visibly marked as unsaved; if the user changes the note while the agent is
writing, the user's newer local content is retained rather than being replaced automatically.

DeepSpace and Grounded Query share rich Markdown fences. `chart` fences render interactive line, bar,
area, scatter, or pie charts with hover details, point editing, safe live equation recalculation,
payload view, and JSON download. In DeepSpace, recalculation updates the chart and its editable JSON
source together, returns to the visual view, and keeps the editor open if the revision cannot be saved.
`card` fences render safe Markdown information cards with metrics,
source links, copy, download, images, and explicit actions. `graph` fences render an interactive
node canvas with connectors, movement, resizing, zoom, grouping, alignment, freehand paths, and JSON
export. `gallery` fences render clickable/downloadable image sequences. Mermaid fences render flow,
UML, architecture, business-model, timeline, and Gantt diagrams with Save artifact, editable source,
JSON and Mermaid source downloads, and SVG, PNG, and PDF exports. SVG exports stay vector-based;
PNG/PDF rasterization uses the diagram viewBox and renders at up to 2× resolution within browser
canvas limits. Inserting an answer into the note editor preserves these surfaces as native rich blocks;
the editor's autosave persists block props across reloads and devices. Generic `json` fences with an
unambiguous visual payload are promoted to the matching surface automatically. Failed image reads
remain recoverable research results, and diagram raster exports sanitize external SVG resources and
show an inline error if the browser still blocks PNG/PDF conversion.

### DeepSpace Library and generated media

Each DeepSpace conversation has a **DeepSpace Library** drawer for separate files only. The active
note remains in its single existing editor and is not duplicated in the drawer. The Library uses a
CodeMirror workspace with line numbers, bracket matching, folding, autocomplete, and language-aware
editing for private Markdown, plain-text, JSON, JavaScript/TypeScript, Python, and Git diff/patch files.
Diff files render added lines in green, removed lines in red, and hunk/header lines distinctly. Markdown
has Edit, Split, and Preview modes with CommonMark/GFM headings, emphasis, links, lists, task checkboxes,
tables, blockquotes, rules, fenced code, diff fences, math, Mermaid diagrams, charts, and standard images.
Raw HTML stays disabled in previews as a security boundary. Message attachments use a separate
chunked upload flow for supported file types and remain private to their conversation. Provider-
generated image, video, and audio also remain authenticated artifacts rather than being exposed
through a public file URL. The `workspace_write` tool can create or update private text files when a
separate file genuinely helps the user’s request; it is tenant-, user-, and conversation-scoped and
never accesses the host filesystem.

Chat attachments become ready once their bytes are safely stored. Text extraction and OCR continue
in the background, so supported images can be sent to a vision-capable model before OCR finishes.
Other file-reading tools become useful as their extraction status reports completion.

The note editor's **Save to Library** action exports the current editor document as Markdown and asks
the user for a filename with an extension before creating a separate Library file. It does not replace
the editor's existing continuous conversation-note save path, so current notes remain safe while a
future source-of-truth file migration is designed and rolled out.

Provider-produced image, video, and audio data is persisted as a private DeepSpace artifact before it
is rendered in chat. Artifact bytes are stored in the configured object store, while PostgreSQL keeps
the authorization metadata and immutable storage locator. The browser fetches the artifact through an
authenticated API endpoint; it never receives a provider URL or object-storage credential. Image,
video, and audio cards support native preview and authenticated download; audio cards draw a waveform
from the actual decoded media samples when the browser supports the codec. Video and audio delivery
supports byte ranges for normal browser seeking. Generation itself remains provider-dependent: Gemini
native image responses (including image-capable Gemini/Nano Banana models) are normalized today; a
future video or audio provider only needs to emit the same typed media event. No synthetic generation
progress or media result is shown when a provider did not actually return one.

Native media turns stream truthful lifecycle states to the chat card: `queued`, `generating`,
`uploading`, `ready`, or `failed`. The UI never invents a percentage when a provider does not report
one. Each ready artifact offers **Regenerate variation**, which reruns the exact source user turn as a
new authenticated DeepSpace request; it preserves the original artifact and re-applies normal model,
tenant, quota, moderation, and policy checks.

The desktop Electron workspace proxy remains single-process because its client registry is process-local.
Do not increase API worker count without first moving that registry to a shared transport.

The current Marketplace uses Composio's live app catalog. Each account supplies its own Composio
project key under Providers → MCP; AverQel encrypts it at rest and scopes it to that account, while the
server decrypts it to call Composio. OAuth apps also require the deployment's public callback origin.
The app catalog and which apps a project can use depend on Composio. The connection flow, security
boundaries, configuration, and deployment checks are documented in
[`backend/docs/capabilities/mcp/03-composio-hosted-mcp.md`](../backend/docs/capabilities/mcp/03-composio-hosted-mcp.md).

The runtime supports the Composio-hosted Streamable HTTP path and its supported SSE fallback. Stdio,
SSH, local process servers, and arbitrary user-entered endpoints are not supported. Existing legacy
provider-profile OAuth connections remain a separate compatibility path; their configuration does
not control the new Composio Marketplace.

## Verification

```bash
pnpm lint
pnpm test
pnpm e2e
pnpm build
```

Browser workflows are split into independently runnable suites:

```bash
pnpm e2e:smoke
pnpm e2e:deepspace
pnpm e2e:documents
```

See [`e2e/README.md`](e2e/README.md) for isolation guarantees, external-run
gates, and failure artifacts.

Local browser E2E starts its own loopback-only Next server, does not load
`.local` runtime settings or reuse an existing server, and sends API proxy
requests to a closed local test sink. External E2E requires both
`DEEPSPACE_E2E_BASE_URL` and `DEEPSPACE_E2E_ALLOW_EXTERNAL=1`. See the
[isolated test run guide](../backend/docs/security/isolated-test-runs.md).

The production Docker image uses Node.js 22 and the repository pins pnpm
10.28.2. Deployment is handled by the checked-in GitHub Actions workflows and
the VPS runbook, not by a Vercel deployment.

See the [Electron guide](../applications/desktop/README.md), the repository
[overview](../README.md), the
[backend documentation index](../backend/docs/README.md), and the root
[contributor guide](../CONTRIBUTING.md) for product, environment, and release details.
