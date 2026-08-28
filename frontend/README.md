# AverQel web workspace

The `frontend/` package is the Next.js web client for AverQel. It runs behind
the AverQel API in production and is also used by the Electron desktop client.

## Getting Started

Use Node.js 22 (the production Docker image uses Node 22) and pnpm 10. The
workspace declaration in `pnpm-workspace.yaml` is required so the checked-in
Vitest 3 toolchain is installed instead of falling back to an incompatible
temporary Vitest version.

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

The repository's normal desktop development command starts the frontend and
Electron together:

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

AverQel includes a curated marketplace for approved remote MCP providers. Users can browse provider
details, reviewed tools, requested OAuth scopes, transport, health, risk labels, and trust badges
from `Dashboard -> MCP Marketplace`.

The supported connection flow is:

```text
Marketplace → provider details → Connect → provider OAuth consent
→ AverQel callback → encrypted per-user connection → catalog refresh
→ connection policy → protected MCP action surface
```

Google and GitHub authentication happens on the provider's authorization page. AverQel never receives
the user's provider password. OAuth access and refresh tokens remain encrypted on the backend and are
never returned to the browser, prompts, logs, or raw MCP events. Disconnect removes the local token
record and requests provider revocation where supported.

MCP connections are tenant- and user-scoped. Connected accounts are automatically available across
the owner's DeepSpace conversations. Tool access is checked through connection ownership,
provider approval, catalog freshness, read-only mode, risk ceiling,
and per-tool mode. `Blocked` wins first; then allowlists and risk/read-only rules apply; `Needs
approval` pauses risky actions; `Always allow` cannot bypass platform or tenant safety rules.

The marketplace distinguishes Official providers from reviewed Community providers. New, Trending, and
Interactive are catalog review attributes, not automatic security approvals. Health and tool previews
are useful status metadata, not uptime guarantees; connected providers can change their live catalog.

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

DeepSpace renders only real streamed evidence in order: provider reasoning, an actual function-tool
call, its streamed arguments, its real result, approval/input requests, and genuine errors. Fixed
backend status prose is not rendered as an agent step. Function arguments are shown incrementally when
a provider sends them. A tool that only returns a final response is shown as running immediately and
completed when that real result arrives; the UI does not fabricate progress.

The model chooses whether a request needs a direct answer, workspace inspection, research, a connected
service, a clarification, or a task plan. It creates a plan with `todo_write` only when a multi-step,
agent-owned outcome benefits from one. Once a real plan exists, DeepSpace enforces its verified lifecycle:
`todo_read`, `todo_mark(in_progress)`, appropriate work tools, `todo_mark(completed, evidence)`,
`todo_check`, then `final`. `observe` and `analyze` remain optional real inspection tools, chosen when
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

### DeepSpace Library and generated media

Each DeepSpace conversation has a **DeepSpace Library** drawer for separate files only. The active
note remains in its single existing editor and is not duplicated in the drawer. The Library uses a
CodeMirror workspace with line numbers, bracket matching, folding, autocomplete, and language-aware
editing for private Markdown, plain-text, JSON, JavaScript/TypeScript, Python, and Git diff/patch files.
Diff files render added lines in green, removed lines in red, and hunk/header lines distinctly. Markdown
has Edit, Split, and Preview modes with CommonMark/GFM headings, emphasis, links, lists, task checkboxes,
tables, blockquotes, rules, fenced code, diff fences, math, Mermaid diagrams, charts, and standard images.
Raw HTML stays disabled in previews as a security boundary. The Library does not
accept arbitrary binary uploads: provider-generated image, video,
and audio remain authenticated artifacts rather than being exposed through a public file URL. The
`workspace_write` tool can create or update the same visible files when a separate file genuinely helps
the user’s request; it is tenant-, user-, and conversation-scoped and never accesses the host
filesystem.

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

This release supports approved remote Streamable HTTP and SSE MCP servers. Stdio, SSH, local process
servers, and arbitrary vendor repositories are not supported. AverQel does not clone vendor MCP
servers: vendors operate their endpoints, while AverQel provides the secure marketplace, OAuth broker,
encryption, tenant isolation, policy enforcement, approval flow, and DeepSpace routing.

Provider OAuth client credentials are configured by the AverQel operator on the VPS. Until the correct
Google or GitHub OAuth profile is configured, the provider can remain visible in the marketplace but
will show `Setup pending` and cannot start user authorization.

## Verification

```bash
pnpm lint
pnpm test
pnpm e2e
pnpm build
```

The production Docker image uses Node.js 22 and the repository pins pnpm
10.28.2. Deployment is handled by the checked-in GitHub Actions workflows and
the VPS runbook, not by a Vercel deployment.

See the [Electron guide](../applications/desktop/README.md), the
[documentation index](../Docs/README.md), and the root
[contributor guide](../CONTRIBUTING.md) for environment and release details.
