# Changelog

## [1.4.1](https://github.com/sainibhaowal/AverQel/compare/v1.4.0...v1.4.1) (2026-10-25)

### Security

- Updated AverQel's LiveKit voice service to a build using Go 1.27.3, addressing
  a security issue in Go's X.509 certificate handling. LiveKit remains at
  v1.13.9; voice behavior and settings are unchanged.

No new user-facing features were added in this patch release.

## [1.4.0] — Unreleased

This release builds on `v1.3.4` with safer long-running DeepSpace workflows, a
user-owned Composio app marketplace, more reliable document processing and
Query behavior, stronger platform-administration safeguards, and a desktop
release workflow that packages AverQel independently. This section covers
changes currently merged to `main`; the release has not been published yet.

**Change range:** [`v1.3.4` through `6a8e336`](https://github.com/sainibhaowal/AverQel/compare/v1.3.4...6a8e3364777826cc9a102b6ef59e8a369dc73e3f), including
[PR #110](https://github.com/sainibhaowal/AverQel/pull/110) and [PR #111](https://github.com/sainibhaowal/AverQel/pull/111).

### Highlights

- **Connect external apps through Composio.** Browse Composio's live toolkit
  catalog, inspect available tools, and connect an app account to DeepSpace.
  Each AverQel user supplies and controls their own Composio project key and
  external account. Tool policies still apply, and actions that write, delete,
  or send external messages require explicit approval.
- **Use Grounded Query more reliably.** Query prompt assembly now preserves
  literal JSON examples instead of interpreting their braces as template
  fields, preventing a prompt-construction failure before the provider call.
  Query file and preview screens also use the shared loading and failure
  states.
- **Continue work across longer DeepSpace runs.** Queue and task state,
  regeneration, activity, provider continuation data, and completed tool
  results are handled more reliably across pauses, retries, reloads, and
  cancellation. Recovery avoids repeating external actions that already
  completed.
- **Use voice as part of a DeepSpace conversation.** Dictation remains
  available for review before sending. Voice conversation submits a transcript
  through the selected DeepSpace chat and speaks new visible answer text while
  the response streams.
- **Protect sensitive administrative actions.** Platform administration now
  applies clearer role and permission checks, session MFA requirements,
  auditable account-security events, and guarded account-erasure and tenant
  purge flows.

### DeepSpace, models, and query workflows

- Added the desktop-only **OpenAI Codex** provider mode. Desktop users can use
  an existing local Codex CLI login or sign in through the system browser.
  OAuth tokens stay in the desktop profile; inference is relayed through an
  authenticated, short-lived desktop connection. The local CLI runs with a
  restricted permission profile.
- Improved provider capability handling. DeepSpace uses model-advertised
  reasoning levels where available, preserves provider reasoning needed for
  follow-up tool calls, and avoids incompatible tool-selection options for
  thinking models. Unsupported reasoning choices are not invented for models
  without reliable capability data.
- Made provider continuation safer across tool calls, approvals, clarifications,
  and queue retries. Required provider reasoning is encrypted before it is
  persisted and is excluded from chat-history responses. If continuation data
  is unavailable, DeepSpace treats the old tool exchange as quoted history and
  preserves successful results so a completed side effect is not silently run
  again.
- Improved the queued-work lifecycle, including resuming interrupted work and
  retrying or regenerating failed turns while keeping completed tool results
  available. DeepSpace refreshes MCP tool definitions before execution; a
  removed or changed tool is not invoked from a stale definition.
- Fixed Query prompt construction so literal JSON examples in prompt templates
  are not processed as `str.format` placeholders. This prevents `KeyError`
  failures before a model request begins.
- Standardized Query loading feedback for Documents Hub search, dataset
  previews, PDF previews, and paginated file browsing, using the shared
  AverQel loading treatment instead of separate ad hoc spinners and skeletons.
- Improved DeepSpace history and live activity restoration. Ordered activity,
  streamed drafts, provider continuation state, and output-rate measurements
  are represented more accurately after reload or resume. Live output rate is
  labeled as an estimate while streaming; provider-reported usage can refine
  the final count.
- Added support for speaking new visible response sentences during voice
  conversation. Hidden reasoning, saved chat history, and raw tool payloads
  are not spoken; interrupting speech playback does not cancel the underlying
  DeepSpace task. Voice requires the configured LiveKit and speech services,
  as well as browser microphone permission.

### Integrations and connected apps

- Added the Composio-hosted MCP catalog, app details, OAuth connection flow,
  tool discovery, connection management, and per-user credential storage. The
  marketplace now uses Composio's live catalog instead of AverQel's bundled
  Google, GitHub, Notion, and Slack connector cards; existing installed
  connections are retained.
- Scoped Composio credentials and hosted-session references to the owning
  tenant and account, encrypted them at rest, and added owner checks around
  replacement and removal. OAuth callbacks are validated against the
  authenticated account and its pending connection request.
- Connected Composio tools to the existing MCP policy and approval broker.
  Model requests receive only the needed tool references, not the full catalog
  or credentials.
- Improved MCP catalog refresh and runtime behavior so optional catalog
  failures do not discard already available tools, and background refresh
  results persist reliably.

### Platform security, privacy, and administration

- Tightened platform-admin route permissions and separated read permissions
  from sensitive actions. Administrative content reads and account-security
  events have safer audit records that exclude prompts, documents, passwords,
  tokens, IP addresses, and device details.
- Required a current MFA-verified administrator session for sensitive
  account-erasure and tenant-purge actions. Tenant purges support a second
  administrator's approval or a delayed, audited self-approval for
  single-administrator installations.
- Added durable cleanup tracking for account-owned object storage during
  account erasure. The admin interface can report and retry failed cleanup
  work without exposing object keys or raw provider errors. Storage cleanup,
  backup expiry, and deletion at external providers remain separate steps.
- Added browser-side encryption workflows for Support and Feedback message
  content and attachments, with per-user keys and an account-owned platform
  key, plus explicit setup and migration state. Only the account that created
  the platform key can unlock cross-tenant Support and Feedback content; the
  current product has no key transfer or recovery flow. Routing metadata
  remains visible to the service, and encrypted attachments cannot be scanned
  server-side. This protection is limited to Support and Feedback and is not
  server-blind encryption for all AverQel data.
- Improved administrator analytics and live system metrics for request and
  error counters, database operations, worker retries, and selected DeepSpace
  activity. The former tenant-usage analytics page and
  `/api/v1/analytics/dashboard` endpoint have been removed; the replacement
  metrics view contains service-operational signals, not per-user usage
  records or an uptime guarantee.
- Improved document detail status polling and classification-history
  presentation. Classification history is requested and shown only for roles
  with the required document-organization access, avoiding unauthorized
  history requests from other users.

### Documents Hub and long-running jobs

- Separated expensive PDF, image, and Office extraction from lightweight
  ingestion. The `ingestion-heavy-worker` consumes its own queue with a default
  concurrency of one and configurable container limits (4 GiB memory and 2
  CPUs by default); the light worker also has its own queue and configurable
  limits (1 GiB and 1 CPU by default). This keeps an extraction workload from
  consuming all worker capacity, while actual headroom still depends on the
  host and deployment settings.
- Hardened document-detail requests for large or busy documents. Status refresh
  is separated from comments, quality, versions, and extracted text; realtime
  updates are coalesced, polling stops at terminal status, concurrent requests
  are guarded, and full text is loaded only when requested after processing is
  complete.
- Added rate-limit-aware cooldowns and bounded backoff for transient network,
  timeout, HTTP 429, and HTTP 503 failures. The document page shows inline
  status and retry controls, preserves the rest of the page when an optional
  request fails, and avoids turning each failed request into a duplicate global
  error toast. This reduces avoidable request bursts; service-side limits and
  outages can still return errors.
- Improved processing state and recovery presentation so a stopped or failed
  job is not shown as healthy or indefinitely processing. When the backend
  reports a recovery checkpoint, the UI can show the saved progress and offer
  a resume action.
- Added automatic retention for expired Support and Feedback records and
  queues their stored attachments for cleanup. Retention defaults to 365 days
  after the last update and is configurable from 30 to 3,650 days. Account
  erasure and tenant-data purge continue to use separate, audited workflows.

### Operations, observability, and storage

- Added a live administrator metrics summary backed by shared Redis counters
  from API and worker processes. The stream reports request and error totals,
  database operations, worker retries and dead letters, and selected DeepSpace
  counters; unavailable or incomplete telemetry is surfaced as such rather
  than represented as a trustworthy zero.
- Prioritized the authenticated metrics summary as an interactive request and
  kept raw Prometheus metrics at background priority. Deployment routing must
  continue to keep the raw metrics endpoint internal.
- Added safe local backup retention to the PostgreSQL, MinIO, and production
  configuration backup scripts. The default is 30 days, supports a configurable
  retention period, and offers a dry-run mode. Pruning covers only recognized
  local AverQel archives and does not configure remote backup or VPS snapshot
  retention.
- Improved worker, database, and request-priority instrumentation while
  keeping metrics low-cardinality and excluding document content, prompts,
  credentials, and raw provider reasoning.

### Desktop, branding, and workspace experience

- Clarified the desktop product boundary: AverQel's Linux and Windows release
  packages contain the AverQel Electron shell and shared frontend. NeoSIS is
  maintained and distributed separately and is not bundled, versioned, or
  fetched by the AverQel package/release workflow.
- Improved desktop login routing, OAuth windows, workspace navigation, and
  installer metadata checks. Initial/deep-link URLs and OAuth windows are
  handled by the Electron shell, and a second launch focuses the existing app
  window. Desktop can route LM Studio and Ollama inference through the
  signed-in local app without bundling model files. Desktop package icons and
  web product marks now use consistent AverQel brand assets.
- Aligned the AverQel icon and wordmark across landing, sign-in, onboarding,
  navigation, dashboard, and desktop surfaces. Refreshed the public product
  guide and landing visuals, improved responsive behavior, and reduced
  background animation and streaming work.
- Improved profile avatars, provider presentation, and visual loading states
  while keeping the shared AverQel theme across the web and desktop surfaces.

### Reliability fixes

- Reduced DeepSpace queue read-lock contention and improved handling of
  retries, cancellation, provider-stream shutdown, activity ordering, and
  completed tool results.
- Preserved provider reasoning across supported adapters and corrected
  reasoning/tool-choice conflicts that could stop a tool-enabled turn before
  execution.
- Hardened dashboard request timeouts, support identity handling, and error
  reporting in the affected admin and workspace surfaces. Document polling now
  honors server retry instructions and uses bounded backoff instead of rapidly
  repeating requests during service pressure.
- Reduced duplicate stream-error reporting and stabilized responsive landing,
  desktop, and browser test behavior.
- Updated the MCP SDK and frontend/backend dependencies, aligned LiveKit with
  the patched OpenTelemetry release, and corrected container image scan and
  isolated MinIO test inputs.

### Release engineering and upgrade notes

- Fixed semantic version calculation for GitHub squash merges: the release
  script now reads valid Conventional Commit titles from PR-body bullets as
  well as commit subjects. For this range, the `feat:` entries calculate the
  next version as `v1.4.0`.
- Removed NeoSIS source checkout and version metadata from the AverQel release
  workflow and download monitoring. The Linux package build now checks its
  Debian package identity and AppStream metadata before publication.
- Added regression coverage around DeepSpace continuation and tool safety,
  Composio credentials and OAuth callbacks, support encryption, administrator
  MFA and deletion approvals, document polling, metrics streaming, backup
  retention, and desktop package boundaries.
- Includes Alembic migrations for platform audit events, feedback/support
  retention and encrypted content, administrator MFA and deletion approvals,
  and per-user Composio credentials. The revisions are
  `20261018_0001`–`20261018_0003` and `20261019_0001`–`20261019_0004`; the last
  repairs the Composio credential schema for installations that recorded the
  earlier platform-only table. Apply the normal database migration procedure
  before deploying the new application version.
- Configure the `ingestion-heavy-worker` alongside the light ingestion worker
  when adopting the updated Compose topology. The resource limits and queue
  concurrency are configurable; size them for the host and leave capacity for
  the API, database, Redis, and other workers.
- The backup scripts' 30-day default retention applies only to their managed
  local backup directory. Configure remote backup and VPS-provider snapshot
  retention separately, and verify a usable backup before reducing retention.
- The former `/api/v1/admin/providers/composio` routes have been removed.
  Users now configure Composio from **Providers → MCP** with their own
  project key. A Composio project key and a working public HTTPS callback
  origin are required for OAuth app connections.
- The tenant-usage analytics page and `/api/v1/analytics/dashboard` API have
  been removed in favor of the operational metrics page and
  `/api/v1/metrics/summary` and `/api/v1/metrics/summary/stream` endpoints.
  Legacy `support_manager` and `feedback_manager` role assignments no longer
  grant access to cross-tenant queues; the platform-admin allowlist and the new
  granular permissions govern that access. The former
  `PUT /api/v1/admin/users/{user_id}/staff-roles` endpoint has also been
  removed.
- Support and Feedback encryption requires the configured platform key and a
  personal key for each user. Cross-tenant support access depends on the
  account that created the platform key; there is no transfer or recovery
  flow. The passphrase cannot be recovered by AverQel. Keep the key-owner
  account available and follow the documented key-handling procedure before
  account erasure. Existing backup snapshots may retain pre-migration plaintext
  until their configured retention expires.
- Existing eligible Support and Feedback messages need the in-browser
  migration after the platform key and each user's personal key are initialized.
  Users without a personal key are skipped and can be migrated after setup.
- Account erasure removes live AverQel records and schedules application-owned
  storage cleanup. It does not instantly erase backups or data already held by
  Composio or other external providers; those follow their own retention and
  revocation controls.

### Further reading

- [DeepSpace user guide](frontend/app/documentation/deepspace/page.tsx)
- [MCP and Composio connection guide](frontend/app/documentation/connectors-mcp/page.tsx)
- [Grounded Query behavior and limits](frontend/app/dashboard/query/README.md)
- [Documents Hub guide](frontend/app/documentation/documents-hub/page.tsx)
- [Platform administration and MFA](backend/docs/platform/06-platform-administration.md)
- [Support and Feedback security](backend/docs/platform/05-feedback-support-notifications.md)
- [Desktop packaging and local providers](applications/desktop/README.md)

## [1.2.0](https://github.com/sainibhaowal/AverQel/compare/v1.1.1...v1.2.0) (2026-08-22)


### Features

* add bounded DeepSpace productivity loop and SearXNG ([91f1c5b](https://github.com/sainibhaowal/AverQel/commit/91f1c5b0523337a698f5f81841b2f9b2532eebb2))
* add DeepSpace processing composer animation ([d844495](https://github.com/sainibhaowal/AverQel/commit/d84449531f521293935a5ed960e291323eda8225))
* add DeepSpace runtime composer effects ([bc690ff](https://github.com/sainibhaowal/AverQel/commit/bc690ffa1621680df1655f051dbaa4573a05259e))
* add dynamic DeepSpace productivity runtime ([030036a](https://github.com/sainibhaowal/AverQel/commit/030036a456043b326fc61de627d206869547c7f9))
* add Google and GitHub application login ([50438ae](https://github.com/sainibhaowal/AverQel/commit/50438ae88d060d28f7b5070eb12ad8dc01442f58))
* add provider icons to OAuth login buttons ([c4460a8](https://github.com/sainibhaowal/AverQel/commit/c4460a83a4efe4a43370e1000a14505a71aff925))
* consolidate DeepSpace productivity runtime and MCP access ([52d9827](https://github.com/sainibhaowal/AverQel/commit/52d9827bbbf00183f1e4b38d793fd1bf455e7909))
* **deepspace:** add governed memory lifecycle ([14ea6f4](https://github.com/sainibhaowal/AverQel/commit/14ea6f4cff1cded46fad06657820d48e49b32c25))
* **deepspace:** add private media artifacts and library ([414e3f5](https://github.com/sainibhaowal/AverQel/commit/414e3f539d6436971e658b1fc8b10c8d9ca849cb))
* **deepspace:** add resilient long-run continuation ([e64bc42](https://github.com/sainibhaowal/AverQel/commit/e64bc4277bf0daf3013340fb2ce30a780cfbd844))
* **deepspace:** add unified Library file previews ([cfa2c49](https://github.com/sainibhaowal/AverQel/commit/cfa2c4905c238a71feeacc9a24bc15e8b66fca6d))
* **deepspace:** add unified library file workspace ([0a0a1d0](https://github.com/sainibhaowal/AverQel/commit/0a0a1d0577f38c52f3cef0db6f0e4dd9e9fc7203))
* **deepspace:** apply production agent policy ([5b6660c](https://github.com/sainibhaowal/AverQel/commit/5b6660c8aa2da41f5f75ca4c5f724e9a6c0c36ec))
* **deepspace:** consolidate memory workspace ([ac7dd35](https://github.com/sainibhaowal/AverQel/commit/ac7dd35ce017d7c8782548a1131ce8b6dbe1cbb3))
* **deepspace:** detach runs from browser streams ([451ff49](https://github.com/sainibhaowal/AverQel/commit/451ff49c265e04ee205255c159fc6a6d1a3771c3))
* **deepspace:** enrich library markdown preview ([4874e7e](https://github.com/sainibhaowal/AverQel/commit/4874e7e4c54a884710b301141b4c7d0a1273e26e))
* **deepspace:** highlight library diff files ([a0d1d23](https://github.com/sainibhaowal/AverQel/commit/a0d1d23749fa76a2e07c05022ef9758f19ffc1be))
* **deepspace:** let models choose task planning ([4a25d18](https://github.com/sainibhaowal/AverQel/commit/4a25d185cb9e3b0f02ead6dfcd6d21ea1f4b0a2a))
* **deepspace:** make library a workspace panel ([3161633](https://github.com/sainibhaowal/AverQel/commit/316163347efa6b15bc5447c693c37657d54a60a1))
* **deepspace:** manage library files ([ddecabe](https://github.com/sainibhaowal/AverQel/commit/ddecabe2a27ad424380c0209777d1db722cb8565))
* **deepspace:** render ordered live agent timeline ([df59ca2](https://github.com/sainibhaowal/AverQel/commit/df59ca23b3e1ad7ab5597633c21cb92c7e3c421f))
* **deepspace:** save editor copies to library ([deaec24](https://github.com/sainibhaowal/AverQel/commit/deaec247b486f0684ace7bf9b92e515e9bb1eee6))
* **deepspace:** ship unified library and quality hardening ([7e7df23](https://github.com/sainibhaowal/AverQel/commit/7e7df23143acca210d72ea1e6ffd9dba66383870))
* **deepspace:** show unified thinking and tool activity ([be1c960](https://github.com/sainibhaowal/AverQel/commit/be1c960d68bc31135b125feada441a3efbad7575))
* **deepspace:** stream agent drafts in note editor ([723f9ca](https://github.com/sainibhaowal/AverQel/commit/723f9cacd6d94edc08982a10cd8cd51ef63b1d1c))
* **deepspace:** stream truthful media lifecycle ([e14cfe0](https://github.com/sainibhaowal/AverQel/commit/e14cfe089d2a9fd225509925f205927b4693a6c2))
* enable DeepSpace tools across chat providers ([09d5abe](https://github.com/sainibhaowal/AverQel/commit/09d5abe7077711a4680402c1cf1c2d221821e90e))
* establish Google Workspace MCP foundation ([5d1eecf](https://github.com/sainibhaowal/AverQel/commit/5d1eecfe7b4a5f246a2706d5965ae5a2f771e31e))
* harden DeepSpace library and interactive runs ([f65d954](https://github.com/sainibhaowal/AverQel/commit/f65d954a362772ea79f4d897fd6c090a8a7af5b4))
* **ingestion:** replace tesseract with PP-OCRv6 ([297011e](https://github.com/sainibhaowal/AverQel/commit/297011e842751c676d9ffe452519110566f89031))
* **landing:** add immersive product visuals ([ac8b110](https://github.com/sainibhaowal/AverQel/commit/ac8b1105f0f22982162058a042f46327fd299a16))
* **landing:** align product story with current workspace ([904b8a8](https://github.com/sainibhaowal/AverQel/commit/904b8a894e3fd1b98dad6505f01d94ac40e26550))
* **landing:** elevate conversion experience ([8bc9aef](https://github.com/sainibhaowal/AverQel/commit/8bc9aef6a577adaa06052b815ecec28f7cbecb61))
* **landing:** expand public product guide ([d440c20](https://github.com/sainibhaowal/AverQel/commit/d440c2083d59669129fd78f963494bc14a13ee2f))
* **mcp:** add marketplace connection controls ([6aa693d](https://github.com/sainibhaowal/AverQel/commit/6aa693d8d4a73b84af7e1c2152d30540ad353c7f))
* **mcp:** add policy and scoped connection APIs ([4ebb945](https://github.com/sainibhaowal/AverQel/commit/4ebb945d19c47e9cfa5e03f63f81f779e19e9d77))
* **mcp:** add provider metadata and connection policies ([9f7baa4](https://github.com/sainibhaowal/AverQel/commit/9f7baa4c65f7978e06bf7d7f7ee13830afac38c4))
* **mcp:** add provider-specific OAuth profiles ([4497e62](https://github.com/sainibhaowal/AverQel/commit/4497e62e27d0840555e33fcd9cbdcd986a84b7df))
* **mcp:** auto-attach connected accounts to DeepSpace ([9831f58](https://github.com/sainibhaowal/AverQel/commit/9831f580fd2a165168cee8461ba78d9c2b7ce35e))
* **mcp:** complete phase 6 marketplace controls ([e48120e](https://github.com/sainibhaowal/AverQel/commit/e48120ef652d5e847cec48d30b5186e80ae8db35))
* **mcp:** enforce native runtime policies ([3332032](https://github.com/sainibhaowal/AverQel/commit/33320323cce4c8609649fdd43ea33d5c4d464366))
* production pipeline v1.0.0 with zero-downtime and release-please ([681f890](https://github.com/sainibhaowal/AverQel/commit/681f890ef4ca0656fa3691055a4aefe2bf3e9da0))


### Bug Fixes

* **api:** prevent dashboard request timeouts ([38dfa7c](https://github.com/sainibhaowal/AverQel/commit/38dfa7cf474950aa33f43301a3655ec3d80033b6))
* **auth:** bound Redis rate-limit timeouts ([5b475fc](https://github.com/sainibhaowal/AverQel/commit/5b475fc176fdba44be7624baa4d00c8f7143dfe3))
* bind local compose to localprod environment ([0bf5b16](https://github.com/sainibhaowal/AverQel/commit/0bf5b16cfab5df8f2182bc1bcad3c46d0cf6fdd7))
* **deepspace:** enforce real task lifecycle ([22cd61d](https://github.com/sainibhaowal/AverQel/commit/22cd61df2f3b745a04ae1615698ef9f27c5ad2d9))
* **deepspace:** fill library workspace and attach file browser ([04c65f8](https://github.com/sainibhaowal/AverQel/commit/04c65f82209b9506bc87352ea252a2e3f2727c62))
* **deepspace:** fill library workspace height ([d724190](https://github.com/sainibhaowal/AverQel/commit/d7241907f25135c19ae671540fbbd56ab70e46ec))
* **deepspace:** identify the assistant as AverQel ([1cb4162](https://github.com/sainibhaowal/AverQel/commit/1cb41624fa067a847bcd332b2cbd7d01db84dd2a))
* **deepspace:** layer model dropdown above runtime border ([c09bf55](https://github.com/sainibhaowal/AverQel/commit/c09bf55e2855b9443be63e0c40ba481f7fafa2a5))
* **deepspace:** negotiate reasoning and MCP tools ([b9238d8](https://github.com/sainibhaowal/AverQel/commit/b9238d8559dad5c0e8db956558266cddc7e9e842))
* **deepspace:** negotiate tool choice for thinking models ([aafe7d4](https://github.com/sainibhaowal/AverQel/commit/aafe7d4555f298d155eb512dda82b1b8c0e2c704))
* **deepspace:** preserve durable activity and markdown tables ([6907358](https://github.com/sainibhaowal/AverQel/commit/6907358647e2b132f1f5da3082489cc206619b1d))
* **deepspace:** preserve task runs and stop provider streams ([249f026](https://github.com/sainibhaowal/AverQel/commit/249f0261253005e825a669bcc864274820c08cd5))
* **deepspace:** recover task tool streams safely ([a96c197](https://github.com/sainibhaowal/AverQel/commit/a96c197e1966c254d2fa24b257179f1c94cfe752))
* **deepspace:** regenerate media from any source turn ([dd1b18d](https://github.com/sainibhaowal/AverQel/commit/dd1b18d8a6f3958875bc905490d0bd421dba56ba))
* **deepspace:** remove duplicate note from library ([cedb716](https://github.com/sainibhaowal/AverQel/commit/cedb7164af1579fbf7c7bed698ad7fb4b8549211))
* **deepspace:** remove synthetic readiness activity ([28f61f0](https://github.com/sainibhaowal/AverQel/commit/28f61f027f8ff2eb124cc951249a2dc535970fe8))
* **deepspace:** replace native library delete prompt ([bd94fe6](https://github.com/sainibhaowal/AverQel/commit/bd94fe65aded5c19e2ad80e82093c98811d49fbf))
* **deepspace:** require explicit Gmail MCP calls ([2cf64d3](https://github.com/sainibhaowal/AverQel/commit/2cf64d337dbabb07c3a6ad3a15fdfb43e5c32cbf))
* **deepspace:** simplify and resize library drawer ([a42bbc1](https://github.com/sainibhaowal/AverQel/commit/a42bbc19b62308a15e61d07e8b82ec1fcfa62b88))
* **deepspace:** switch directly to chat library split ([3beae17](https://github.com/sainibhaowal/AverQel/commit/3beae17b122e635fd690259ae06824f3d6bd9734))
* **deepspace:** theme and collapse library files ([82a3888](https://github.com/sainibhaowal/AverQel/commit/82a38887d683fd133bd6b9e786e178f82d2a1793))
* **deploy:** exclude stale Next build cache ([d1c1edf](https://github.com/sainibhaowal/AverQel/commit/d1c1edfb57144065a3b517f98ebb2426d6839fdf))
* **frontend:** harden hydration stability ([58a0aec](https://github.com/sainibhaowal/AverQel/commit/58a0aecc76c79fa76c8ca79f97c25684916f4cd4))
* guard Mermaid parser error output ([e6d7c94](https://github.com/sainibhaowal/AverQel/commit/e6d7c946353d9acc20ec57043f28d8f0d523a2d5))
* harden DeepSpace memory and MCP E2E checks ([f466bf9](https://github.com/sainibhaowal/AverQel/commit/f466bf9030dfdb8d1527ab6c98abfd632d4e8812))
* isolate API work from request loop ([a4ba849](https://github.com/sainibhaowal/AverQel/commit/a4ba8497c59190656d6353f21643df80bf0aaa82))
* keep complex DeepSpace tasks executing ([1934341](https://github.com/sainibhaowal/AverQel/commit/19343415e4ab6c2bf0a50a5e14ec49d1b1b88a20))
* keep composer surface unchanged during processing ([106cff0](https://github.com/sainibhaowal/AverQel/commit/106cff0caafc3c0a0cff529f35edea03031ebe88))
* keep MCP tools when optional catalog calls fail ([e55161c](https://github.com/sainibhaowal/AverQel/commit/e55161c2080e09004f93e47b402387e413c392fe))
* make DeepSpace editor toolbar menus clickable ([a0ebbee](https://github.com/sainibhaowal/AverQel/commit/a0ebbee2c55fdec359d6987c31e9e5f3774eeaee))
* make MCP catalog worker persist refresh results ([6e20a43](https://github.com/sainibhaowal/AverQel/commit/6e20a4344dfcb07001ea2167fb733e9babe34593))
* make note exports and workspace layout interactive ([7b9a332](https://github.com/sainibhaowal/AverQel/commit/7b9a33280a0200d700b68b97a9d7169512348cb4))
* make pip-audit report-only and fix release-please pr json syntax ([35db5f8](https://github.com/sainibhaowal/AverQel/commit/35db5f83c73bf5f15c8a34b98c4a2d72f469ab50))
* make pytest unit_no_db report-only for fast CI ([ef5ac80](https://github.com/sainibhaowal/AverQel/commit/ef5ac803abb7d430c9f388b51c23bc6f78d712fc))
* **mcp:** streamline OAuth return and active chat context ([81ef8e6](https://github.com/sainibhaowal/AverQel/commit/81ef8e6edbcdd087c6395dd9ae9125fdae5c5015))
* preserve DeepSpace timeline across reloads ([e874715](https://github.com/sainibhaowal/AverQel/commit/e8747153e2cd87906cbab68ffd910730364e6802))
* **providers:** preserve reasoning across all adapters ([0c65ce2](https://github.com/sainibhaowal/AverQel/commit/0c65ce2a6b0eb446b68494b45f4edad450801342))
* **providers:** prevent reasoning conflicts with required tools ([2298ea5](https://github.com/sainibhaowal/AverQel/commit/2298ea5520d494502e01e181703efea2f4c1dae4))
* refresh persisted MCP OAuth tokens in workers ([12811cd](https://github.com/sainibhaowal/AverQel/commit/12811cd6d67755f7743646a27c7cef4efe219b41))
* release-please use v* tags not averqel-v* and make VPS deploy not require git ([138a094](https://github.com/sainibhaowal/AverQel/commit/138a094fef9bbe59ec762d5e130fb27c7be40bf6))
* **reliability:** prevent database lock starvation ([8691872](https://github.com/sainibhaowal/AverQel/commit/8691872d53e3ffa0eaab7cdf9cc02f68131edb92))
* restore async MCP catalog discovery ([5b029f4](https://github.com/sainibhaowal/AverQel/commit/5b029f4e4c17c3a6a61c7f9082ca3a00807a2800))
* stabilize DeepSpace streaming and composer animation ([05aa652](https://github.com/sainibhaowal/AverQel/commit/05aa652472ad4890b796e4bfc3a963af6eae3b39))
* stabilize ingestion and refresh dashboard surfaces ([033adc2](https://github.com/sainibhaowal/AverQel/commit/033adc2cbb30c47f55e39ac56721e59b8e3b4037))
* **ui:** add rounded MCP filter menus ([4b58498](https://github.com/sainibhaowal/AverQel/commit/4b58498e3c56150b57303fabff3099e7fd00f498))
* **ui:** make MCP marketplace full width ([e9ff5fd](https://github.com/sainibhaowal/AverQel/commit/e9ff5fd769c72af3f1f408c4f0c70a1ff8f13aa3))
* **ui:** remove duplicate DeepSpace stream errors ([9de6a82](https://github.com/sainibhaowal/AverQel/commit/9de6a82ec182c55f8ec0dbe95f38526abcb4825e))
* **ui:** remove native memory importance spinner ([7bc88aa](https://github.com/sainibhaowal/AverQel/commit/7bc88aa9413d6c0b1f1e5c5126bf3e0aa5da2ae1))
* **ui:** replace DeepSpace memory scope select ([d071335](https://github.com/sainibhaowal/AverQel/commit/d07133597fb3a67b0957f62cf0dbc2622ea33ab0))
* **ui:** simplify DeepSpace action animation ([5519d5f](https://github.com/sainibhaowal/AverQel/commit/5519d5f16a46a5706ac05e36e373330b9230c680))
* **ui:** type MCP sort filter state ([a3d472c](https://github.com/sainibhaowal/AverQel/commit/a3d472c2dcaad2c6749cbe6aac54c5ba0bdd0610))
* update setuptools to 83.0.0 and ignore json-repair GHSA for livekit-agents compat ([a0092c4](https://github.com/sainibhaowal/AverQel/commit/a0092c4d5170a7e215f1b2302fb6406dd43feaf4))

## [1.1.1](https://github.com/sainibhaowal/AverQel/compare/averqel-v1.1.0...averqel-v1.1.1) (2026-08-22)


### Bug Fixes

* make pytest unit_no_db report-only for fast CI ([ef5ac80](https://github.com/sainibhaowal/AverQel/commit/ef5ac803abb7d430c9f388b51c23bc6f78d712fc))

## [1.1.0](https://github.com/sainibhaowal/AverQel/compare/averqel-v1.0.0...averqel-v1.1.0) (2026-08-21)


### Features

* add bounded DeepSpace productivity loop and SearXNG ([91f1c5b](https://github.com/sainibhaowal/AverQel/commit/91f1c5b0523337a698f5f81841b2f9b2532eebb2))
* add DeepSpace processing composer animation ([d844495](https://github.com/sainibhaowal/AverQel/commit/d84449531f521293935a5ed960e291323eda8225))
* add DeepSpace runtime composer effects ([bc690ff](https://github.com/sainibhaowal/AverQel/commit/bc690ffa1621680df1655f051dbaa4573a05259e))
* add dynamic DeepSpace productivity runtime ([030036a](https://github.com/sainibhaowal/AverQel/commit/030036a456043b326fc61de627d206869547c7f9))
* add Google and GitHub application login ([50438ae](https://github.com/sainibhaowal/AverQel/commit/50438ae88d060d28f7b5070eb12ad8dc01442f58))
* add provider icons to OAuth login buttons ([c4460a8](https://github.com/sainibhaowal/AverQel/commit/c4460a83a4efe4a43370e1000a14505a71aff925))
* consolidate DeepSpace productivity runtime and MCP access ([52d9827](https://github.com/sainibhaowal/AverQel/commit/52d9827bbbf00183f1e4b38d793fd1bf455e7909))
* **deepspace:** add governed memory lifecycle ([14ea6f4](https://github.com/sainibhaowal/AverQel/commit/14ea6f4cff1cded46fad06657820d48e49b32c25))
* **deepspace:** add private media artifacts and library ([414e3f5](https://github.com/sainibhaowal/AverQel/commit/414e3f539d6436971e658b1fc8b10c8d9ca849cb))
* **deepspace:** add resilient long-run continuation ([e64bc42](https://github.com/sainibhaowal/AverQel/commit/e64bc4277bf0daf3013340fb2ce30a780cfbd844))
* **deepspace:** add unified Library file previews ([cfa2c49](https://github.com/sainibhaowal/AverQel/commit/cfa2c4905c238a71feeacc9a24bc15e8b66fca6d))
* **deepspace:** add unified library file workspace ([0a0a1d0](https://github.com/sainibhaowal/AverQel/commit/0a0a1d0577f38c52f3cef0db6f0e4dd9e9fc7203))
* **deepspace:** apply production agent policy ([5b6660c](https://github.com/sainibhaowal/AverQel/commit/5b6660c8aa2da41f5f75ca4c5f724e9a6c0c36ec))
* **deepspace:** consolidate memory workspace ([ac7dd35](https://github.com/sainibhaowal/AverQel/commit/ac7dd35ce017d7c8782548a1131ce8b6dbe1cbb3))
* **deepspace:** detach runs from browser streams ([451ff49](https://github.com/sainibhaowal/AverQel/commit/451ff49c265e04ee205255c159fc6a6d1a3771c3))
* **deepspace:** enrich library markdown preview ([4874e7e](https://github.com/sainibhaowal/AverQel/commit/4874e7e4c54a884710b301141b4c7d0a1273e26e))
* **deepspace:** highlight library diff files ([a0d1d23](https://github.com/sainibhaowal/AverQel/commit/a0d1d23749fa76a2e07c05022ef9758f19ffc1be))
* **deepspace:** let models choose task planning ([4a25d18](https://github.com/sainibhaowal/AverQel/commit/4a25d185cb9e3b0f02ead6dfcd6d21ea1f4b0a2a))
* **deepspace:** make library a workspace panel ([3161633](https://github.com/sainibhaowal/AverQel/commit/316163347efa6b15bc5447c693c37657d54a60a1))
* **deepspace:** manage library files ([ddecabe](https://github.com/sainibhaowal/AverQel/commit/ddecabe2a27ad424380c0209777d1db722cb8565))
* **deepspace:** render ordered live agent timeline ([df59ca2](https://github.com/sainibhaowal/AverQel/commit/df59ca23b3e1ad7ab5597633c21cb92c7e3c421f))
* **deepspace:** save editor copies to library ([deaec24](https://github.com/sainibhaowal/AverQel/commit/deaec247b486f0684ace7bf9b92e515e9bb1eee6))
* **deepspace:** ship unified library and quality hardening ([7e7df23](https://github.com/sainibhaowal/AverQel/commit/7e7df23143acca210d72ea1e6ffd9dba66383870))
* **deepspace:** show unified thinking and tool activity ([be1c960](https://github.com/sainibhaowal/AverQel/commit/be1c960d68bc31135b125feada441a3efbad7575))
* **deepspace:** stream agent drafts in note editor ([723f9ca](https://github.com/sainibhaowal/AverQel/commit/723f9cacd6d94edc08982a10cd8cd51ef63b1d1c))
* **deepspace:** stream truthful media lifecycle ([e14cfe0](https://github.com/sainibhaowal/AverQel/commit/e14cfe089d2a9fd225509925f205927b4693a6c2))
* enable DeepSpace tools across chat providers ([09d5abe](https://github.com/sainibhaowal/AverQel/commit/09d5abe7077711a4680402c1cf1c2d221821e90e))
* establish Google Workspace MCP foundation ([5d1eecf](https://github.com/sainibhaowal/AverQel/commit/5d1eecfe7b4a5f246a2706d5965ae5a2f771e31e))
* harden DeepSpace library and interactive runs ([f65d954](https://github.com/sainibhaowal/AverQel/commit/f65d954a362772ea79f4d897fd6c090a8a7af5b4))
* **ingestion:** replace tesseract with PP-OCRv6 ([297011e](https://github.com/sainibhaowal/AverQel/commit/297011e842751c676d9ffe452519110566f89031))
* **landing:** add immersive product visuals ([ac8b110](https://github.com/sainibhaowal/AverQel/commit/ac8b1105f0f22982162058a042f46327fd299a16))
* **landing:** align product story with current workspace ([904b8a8](https://github.com/sainibhaowal/AverQel/commit/904b8a894e3fd1b98dad6505f01d94ac40e26550))
* **landing:** elevate conversion experience ([8bc9aef](https://github.com/sainibhaowal/AverQel/commit/8bc9aef6a577adaa06052b815ecec28f7cbecb61))
* **landing:** expand public product guide ([d440c20](https://github.com/sainibhaowal/AverQel/commit/d440c2083d59669129fd78f963494bc14a13ee2f))
* **mcp:** add marketplace connection controls ([6aa693d](https://github.com/sainibhaowal/AverQel/commit/6aa693d8d4a73b84af7e1c2152d30540ad353c7f))
* **mcp:** add policy and scoped connection APIs ([4ebb945](https://github.com/sainibhaowal/AverQel/commit/4ebb945d19c47e9cfa5e03f63f81f779e19e9d77))
* **mcp:** add provider metadata and connection policies ([9f7baa4](https://github.com/sainibhaowal/AverQel/commit/9f7baa4c65f7978e06bf7d7f7ee13830afac38c4))
* **mcp:** add provider-specific OAuth profiles ([4497e62](https://github.com/sainibhaowal/AverQel/commit/4497e62e27d0840555e33fcd9cbdcd986a84b7df))
* **mcp:** auto-attach connected accounts to DeepSpace ([9831f58](https://github.com/sainibhaowal/AverQel/commit/9831f580fd2a165168cee8461ba78d9c2b7ce35e))
* **mcp:** complete phase 6 marketplace controls ([e48120e](https://github.com/sainibhaowal/AverQel/commit/e48120ef652d5e847cec48d30b5186e80ae8db35))
* **mcp:** enforce native runtime policies ([3332032](https://github.com/sainibhaowal/AverQel/commit/33320323cce4c8609649fdd43ea33d5c4d464366))
* production pipeline v1.0.0 with zero-downtime and release-please ([681f890](https://github.com/sainibhaowal/AverQel/commit/681f890ef4ca0656fa3691055a4aefe2bf3e9da0))


### Bug Fixes

* **api:** prevent dashboard request timeouts ([38dfa7c](https://github.com/sainibhaowal/AverQel/commit/38dfa7cf474950aa33f43301a3655ec3d80033b6))
* **auth:** bound Redis rate-limit timeouts ([5b475fc](https://github.com/sainibhaowal/AverQel/commit/5b475fc176fdba44be7624baa4d00c8f7143dfe3))
* bind local compose to localprod environment ([0bf5b16](https://github.com/sainibhaowal/AverQel/commit/0bf5b16cfab5df8f2182bc1bcad3c46d0cf6fdd7))
* **deepspace:** enforce real task lifecycle ([22cd61d](https://github.com/sainibhaowal/AverQel/commit/22cd61df2f3b745a04ae1615698ef9f27c5ad2d9))
* **deepspace:** fill library workspace and attach file browser ([04c65f8](https://github.com/sainibhaowal/AverQel/commit/04c65f82209b9506bc87352ea252a2e3f2727c62))
* **deepspace:** fill library workspace height ([d724190](https://github.com/sainibhaowal/AverQel/commit/d7241907f25135c19ae671540fbbd56ab70e46ec))
* **deepspace:** identify the assistant as AverQel ([1cb4162](https://github.com/sainibhaowal/AverQel/commit/1cb41624fa067a847bcd332b2cbd7d01db84dd2a))
* **deepspace:** layer model dropdown above runtime border ([c09bf55](https://github.com/sainibhaowal/AverQel/commit/c09bf55e2855b9443be63e0c40ba481f7fafa2a5))
* **deepspace:** negotiate reasoning and MCP tools ([b9238d8](https://github.com/sainibhaowal/AverQel/commit/b9238d8559dad5c0e8db956558266cddc7e9e842))
* **deepspace:** negotiate tool choice for thinking models ([aafe7d4](https://github.com/sainibhaowal/AverQel/commit/aafe7d4555f298d155eb512dda82b1b8c0e2c704))
* **deepspace:** preserve durable activity and markdown tables ([6907358](https://github.com/sainibhaowal/AverQel/commit/6907358647e2b132f1f5da3082489cc206619b1d))
* **deepspace:** preserve task runs and stop provider streams ([249f026](https://github.com/sainibhaowal/AverQel/commit/249f0261253005e825a669bcc864274820c08cd5))
* **deepspace:** recover task tool streams safely ([a96c197](https://github.com/sainibhaowal/AverQel/commit/a96c197e1966c254d2fa24b257179f1c94cfe752))
* **deepspace:** regenerate media from any source turn ([dd1b18d](https://github.com/sainibhaowal/AverQel/commit/dd1b18d8a6f3958875bc905490d0bd421dba56ba))
* **deepspace:** remove duplicate note from library ([cedb716](https://github.com/sainibhaowal/AverQel/commit/cedb7164af1579fbf7c7bed698ad7fb4b8549211))
* **deepspace:** remove synthetic readiness activity ([28f61f0](https://github.com/sainibhaowal/AverQel/commit/28f61f027f8ff2eb124cc951249a2dc535970fe8))
* **deepspace:** replace native library delete prompt ([bd94fe6](https://github.com/sainibhaowal/AverQel/commit/bd94fe65aded5c19e2ad80e82093c98811d49fbf))
* **deepspace:** require explicit Gmail MCP calls ([2cf64d3](https://github.com/sainibhaowal/AverQel/commit/2cf64d337dbabb07c3a6ad3a15fdfb43e5c32cbf))
* **deepspace:** simplify and resize library drawer ([a42bbc1](https://github.com/sainibhaowal/AverQel/commit/a42bbc19b62308a15e61d07e8b82ec1fcfa62b88))
* **deepspace:** switch directly to chat library split ([3beae17](https://github.com/sainibhaowal/AverQel/commit/3beae17b122e635fd690259ae06824f3d6bd9734))
* **deepspace:** theme and collapse library files ([82a3888](https://github.com/sainibhaowal/AverQel/commit/82a38887d683fd133bd6b9e786e178f82d2a1793))
* **deploy:** exclude stale Next build cache ([d1c1edf](https://github.com/sainibhaowal/AverQel/commit/d1c1edfb57144065a3b517f98ebb2426d6839fdf))
* **frontend:** harden hydration stability ([58a0aec](https://github.com/sainibhaowal/AverQel/commit/58a0aecc76c79fa76c8ca79f97c25684916f4cd4))
* guard Mermaid parser error output ([e6d7c94](https://github.com/sainibhaowal/AverQel/commit/e6d7c946353d9acc20ec57043f28d8f0d523a2d5))
* harden DeepSpace memory and MCP E2E checks ([f466bf9](https://github.com/sainibhaowal/AverQel/commit/f466bf9030dfdb8d1527ab6c98abfd632d4e8812))
* isolate API work from request loop ([a4ba849](https://github.com/sainibhaowal/AverQel/commit/a4ba8497c59190656d6353f21643df80bf0aaa82))
* keep complex DeepSpace tasks executing ([1934341](https://github.com/sainibhaowal/AverQel/commit/19343415e4ab6c2bf0a50a5e14ec49d1b1b88a20))
* keep composer surface unchanged during processing ([106cff0](https://github.com/sainibhaowal/AverQel/commit/106cff0caafc3c0a0cff529f35edea03031ebe88))
* keep MCP tools when optional catalog calls fail ([e55161c](https://github.com/sainibhaowal/AverQel/commit/e55161c2080e09004f93e47b402387e413c392fe))
* make DeepSpace editor toolbar menus clickable ([a0ebbee](https://github.com/sainibhaowal/AverQel/commit/a0ebbee2c55fdec359d6987c31e9e5f3774eeaee))
* make MCP catalog worker persist refresh results ([6e20a43](https://github.com/sainibhaowal/AverQel/commit/6e20a4344dfcb07001ea2167fb733e9babe34593))
* make note exports and workspace layout interactive ([7b9a332](https://github.com/sainibhaowal/AverQel/commit/7b9a33280a0200d700b68b97a9d7169512348cb4))
* make pip-audit report-only and fix release-please pr json syntax ([35db5f8](https://github.com/sainibhaowal/AverQel/commit/35db5f83c73bf5f15c8a34b98c4a2d72f469ab50))
* **mcp:** streamline OAuth return and active chat context ([81ef8e6](https://github.com/sainibhaowal/AverQel/commit/81ef8e6edbcdd087c6395dd9ae9125fdae5c5015))
* preserve DeepSpace timeline across reloads ([e874715](https://github.com/sainibhaowal/AverQel/commit/e8747153e2cd87906cbab68ffd910730364e6802))
* **providers:** preserve reasoning across all adapters ([0c65ce2](https://github.com/sainibhaowal/AverQel/commit/0c65ce2a6b0eb446b68494b45f4edad450801342))
* **providers:** prevent reasoning conflicts with required tools ([2298ea5](https://github.com/sainibhaowal/AverQel/commit/2298ea5520d494502e01e181703efea2f4c1dae4))
* refresh persisted MCP OAuth tokens in workers ([12811cd](https://github.com/sainibhaowal/AverQel/commit/12811cd6d67755f7743646a27c7cef4efe219b41))
* **reliability:** prevent database lock starvation ([8691872](https://github.com/sainibhaowal/AverQel/commit/8691872d53e3ffa0eaab7cdf9cc02f68131edb92))
* restore async MCP catalog discovery ([5b029f4](https://github.com/sainibhaowal/AverQel/commit/5b029f4e4c17c3a6a61c7f9082ca3a00807a2800))
* stabilize DeepSpace streaming and composer animation ([05aa652](https://github.com/sainibhaowal/AverQel/commit/05aa652472ad4890b796e4bfc3a963af6eae3b39))
* stabilize ingestion and refresh dashboard surfaces ([033adc2](https://github.com/sainibhaowal/AverQel/commit/033adc2cbb30c47f55e39ac56721e59b8e3b4037))
* **ui:** add rounded MCP filter menus ([4b58498](https://github.com/sainibhaowal/AverQel/commit/4b58498e3c56150b57303fabff3099e7fd00f498))
* **ui:** make MCP marketplace full width ([e9ff5fd](https://github.com/sainibhaowal/AverQel/commit/e9ff5fd769c72af3f1f408c4f0c70a1ff8f13aa3))
* **ui:** remove duplicate DeepSpace stream errors ([9de6a82](https://github.com/sainibhaowal/AverQel/commit/9de6a82ec182c55f8ec0dbe95f38526abcb4825e))
* **ui:** remove native memory importance spinner ([7bc88aa](https://github.com/sainibhaowal/AverQel/commit/7bc88aa9413d6c0b1f1e5c5126bf3e0aa5da2ae1))
* **ui:** replace DeepSpace memory scope select ([d071335](https://github.com/sainibhaowal/AverQel/commit/d07133597fb3a67b0957f62cf0dbc2622ea33ab0))
* **ui:** simplify DeepSpace action animation ([5519d5f](https://github.com/sainibhaowal/AverQel/commit/5519d5f16a46a5706ac05e36e373330b9230c680))
* **ui:** type MCP sort filter state ([a3d472c](https://github.com/sainibhaowal/AverQel/commit/a3d472c2dcaad2c6749cbe6aac54c5ba0bdd0610))
* update setuptools to 83.0.0 and ignore json-repair GHSA for livekit-agents compat ([a0092c4](https://github.com/sainibhaowal/AverQel/commit/a0092c4d5170a7e215f1b2302fb6406dd43feaf4))
