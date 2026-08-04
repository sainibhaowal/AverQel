This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

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

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

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

When an agent uses the DeepSpace `write` tool, the note panel also renders the real streamed Markdown
arguments as an in-editor **AverQel is writing** preview. The preview is not persisted token by token:
only the validated, tenant-scoped write-tool result replaces or appends the durable note. If a stream
fails, the draft remains visibly marked as unsaved; if the user changes the note while the agent is
writing, the user's newer local content is retained rather than being replaced automatically.

### DeepSpace Library and generated media

Each DeepSpace conversation has a **DeepSpace Library** drawer for separate files only. The active
note remains in its single existing editor and is not duplicated in the drawer. Users can create, edit,
preview, and save private Markdown, plain-text, JSON, JavaScript, and Python files. The
`workspace_write` tool can create or update the same visible files when a separate file genuinely helps
the user’s request; it is tenant-, user-, and conversation-scoped and never accesses the host
filesystem.

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

The desktop/Tauri workspace proxy remains single-process because its client registry is process-local.
Do not increase API worker count without first moving that registry to a shared transport.

This release supports approved remote Streamable HTTP and SSE MCP servers. Stdio, SSH, local process
servers, and arbitrary vendor repositories are not supported. AverQel does not clone vendor MCP
servers: vendors operate their endpoints, while AverQel provides the secure marketplace, OAuth broker,
encryption, tenant isolation, policy enforcement, approval flow, and DeepSpace routing.

Provider OAuth client credentials are configured by the AverQel operator on the VPS. Until the correct
Google or GitHub OAuth profile is configured, the provider can remain visible in the marketplace but
will show `Setup pending` and cannot start user authorization.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
