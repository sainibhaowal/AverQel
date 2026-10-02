# 05. DeepSpace private operations runbook

## Scope and safety

This runbook covers the existing AverQel API, Redis, PostgreSQL, workers, and
DeepSpace dashboard. It does not require an external monitoring service. Never
place production tokens, tenant identifiers, prompts, provider keys, or files in
benchmark output, issue trackers, or dashboards.

## User-selected provider protection

DeepSpace never changes a selected model automatically. Repeated failures open a
short Redis circuit only for that tenant/provider/model. The UI reports the
condition; the user may retry later or select another model explicitly.

## DeepSpace private dashboard

The existing DeepSpace screen displays a private provider-health summary sourced
from the authenticated `GET /deepspace/chats/operational-summary` endpoint. It
shows only the current user's tenant-scoped recent sample size, failure rate,
and p50/p95 latency. It must never display prompts, responses, API keys, raw
provider errors, or another tenant's measurements.

The activity timeline receives only truthful server lifecycle events:
`resolving_provider`, `provider_ready`, `finalizing`, and
`provider_unavailable`. These events are operational status, not model hidden
reasoning.

## Storage retention and cleanup

The exact retention policy is documented in
[`07-deepspace-retention-policy.md`](07-deepspace-retention-policy.md). In summary,
the daily `maintenance.retention_cleanup` task handles only separate technical
retention (idempotency, deletion-request, and audit policies). Legacy DeepSpace
event rows and durable context epochs without lifecycle identity are preserved.

Storage exposes Off/30/60/90 days. The monthly
`maintenance.storage_retention_scan` task creates tenant-scoped preview and
protection decisions only. It does not delete conversations, chat messages,
active runs, queued turns, completed answers, artifacts, provider credentials,
or object-storage objects.

Metadata-only source archive and DeepSpace restore are implemented for local or
staging when `AKS_STORAGE_RETENTION_AUTOMATIC_ARCHIVE_ENABLED=true`. Production
and VPS remain disabled until deployment and external staging restore
verification are complete. Permanent purge remains disabled.
Browser navigation, reloads, and dropped SSE connections never count as cleanup
triggers.

## Queue failure and recovery behavior

DeepSpace queue execution is fail-stop. If a real agent/tool execution returns
an error, the current queued turn is saved as `failed`, its tool/error frames
remain in the durable event history, and the conversation queue is paused. No
later queued turn is dispatched automatically. The composer shows the failure
reason and provides **Resume queue** after the user has reviewed or fixed the
problem. A user may also send a separate normal run-now message while the
queue is paused; that message does not consume or reorder the saved queue.

For an automatic failure pause, **Retry checkpoint** or **Retry failed &
resume** creates a new durable attempt linked to the failed request. The
original failed row and error remain visible. The retry reuses the same
assistant turn's last successful runtime tool results and asks the agent to
continue from that checkpoint, so completed side effects are not blindly
repeated. A user can instead steer another still-queued item while paused;
that promoted item runs without retrying the failed checkpoint.

The user may pause a queue at any time. Pausing requests cancellation of the
currently running queued turn and prevents later turns from starting. Resume
dispatches the highest-priority queued item, with steered items ahead of normal
FIFO items. Steering a queued item also resumes an automatically paused queue
after the active turn has been stopped.

Once the queue is resumed and work is active, every new composer message is
saved as another queue item. It is never sent as an independent run while the
queue is active. Independent run-now messages are available only while the
queue is paused and no queued turn is still stopping.

If a dispatcher claims a turn and dies before submitting the worker, the claim
is released immediately when broker submission reports an error. A periodic
maintenance heartbeat also recovers claims older than ten minutes: it
re-queues a claim with no runtime worker, or preserves a completed/cancelled
worker result; if the matching worker failed, it marks that turn failed and
pauses the queue. Returning to DeepSpace also runs this recovery check before
redispatching recovered work.

## Failed file ingestion

Use the existing authenticated `POST /documents/{document_id}/reingest` action.
It is an explicit, tenant-authorized retry: it clears stale chunks, records a
new ingestion job, audits the action, and preserves prior job evidence. Do not
bulk retry dead-lettered documents without identifying the parser/storage cause.

## Database migration and worker rollout

For the current DeepSpace runtime work, apply migrations before starting or
restarting API and worker processes:

```bash
cd /home/ravi/Projects/AverQel/backend
source .venv/bin/activate
alembic upgrade head
```

This also applies `20260925_0001_storage_retention_lifecycle`, an additive
migration that defaults every tenant to retention `off`. Do not run the global
`alembic` command unless the backend virtual environment is active; the
repository's Alembic dependency is installed in `.venv`.

Confirm that the following current-worktree migrations are present in the
applied revision history:

- `20260916_0001_deepspace_queued_turns`
- `20260916_0002_deepspace_request_metrics`
- `20260917_0001_cascade_deepspace_runtime_and_snapshots`
- `20260918_0001_deepspace_context_summaries`
- `20260920_0001_deepspace_context_epochs`
- `20260922_0001_deepspace_queue_controls`
- `20260923_0001_deepspace_checkpoint_retries`
- `20260924_0001_tenant_storage_allocations`
- `20260925_0001_storage_retention_lifecycle`
- `20260926_0001_storage_reservations_archive_reconciliation`
- `20260927_0001_retention_checkpoints`
- `20260928_0001_retention_protections_and_run_links`

Restart API and workers together after a migration that changes queue,
runtime, provider, or event behavior. If a migration fails, stop the rollout,
preserve the database error, and restore the previous application image; do
not delete migration rows or manually edit `alembic_version`.

## Web search versus webpage reading

`web_search` returns search results and snippets. It does not prove that a
page was opened. A fetched page must be reported only after the `url_read`
tool returns bounded content and a source URL. The normal research routing
exposes `url_read` alongside `web_search`, and direct HTTPS URLs can use it
without search-provider selection.

For JavaScript-heavy public pages, deploy and smoke-test the optional
`research-browser` profile. Static extraction calls it only when the page looks
like an empty JavaScript shell. Keep cookies, logins, downloads, private-network
targets, and side effects blocked. If the renderer is unavailable, static
evidence is retained when available; otherwise the UI must say that the source
was not fetched rather than presenting a search snippet as page content.

## Staging load validation

Use only staging credentials and synthetic files:

```bash
python backend/scripts/benchmark_library_concurrency.py --dry-run --token staging --tenant-id staging --conversation-id staging --file-id staging
python backend/scripts/staging_durable_load.py --help
```

Before changing concurrency, record p50/p95 latency, error rate, queue depth,
worker retries, dead letters, Redis availability, and database saturation. Roll
back the worker-concurrency value if p95 increases materially or any tenant
isolation/authentication check fails.

For DeepSpace latency comparison, use the read-only observed-summary benchmark
after a controlled set of synthetic staging turns has completed:

```bash
python backend/scripts/benchmark_deepspace_latency.py --dry-run --token staging --tenant-id staging
python backend/scripts/benchmark_deepspace_latency.py --base-url https://staging.example/api/v1 --token "$STAGING_TOKEN" --tenant-id "$STAGING_TENANT" --allow-staging
```

The non-dry run only reads the authenticated, tenant-scoped
`GET /deepspace/chats/operational-summary` endpoint. It does not create turns,
send prompts, call providers, or mutate storage. Never pass production URLs or
credentials unless an approved change window explicitly authorizes it; the
script rejects non-local hosts without `--allow-staging`.

For an approved staging timing run that measures actual streaming, use the
separate, explicitly write-enabled mode with a synthetic prompt and a bounded
request count:

```bash
python backend/scripts/benchmark_deepspace_latency.py \
  --base-url https://staging.example/api/v1 \
  --token "$STAGING_TOKEN" \
  --tenant-id "$STAGING_TENANT" \
  --requests 3 \
  --allow-staging \
  --write-staging-data \
  --stream \
  --prompt "Return exactly BENCHMARK_OK."
```

This mode creates only the explicitly requested synthetic staging turns and
records status, event count, time to first event, and total latency. It rejects
production-like hostnames and is never a production certification by itself.

## LM Studio endpoint compatibility

Configure an LM Studio provider with either its server root
(`http://host:1234`) or its OpenAI-compatible root (`http://host:1234/v1`).
The LM Studio adapter normalizes both forms to `/v1` for chat, streaming, and
fallback requests. This preserves the selected model, messages, tool protocol,
and DeepSpace policy; it only avoids the legacy endpoint that can return an
empty HTTP 200 stream. Validate a new local model with a disposable tenant and
the bounded streaming benchmark above before assigning it to a real user.

## Browser validation

Run authenticated Playwright only against a staging instance with short-lived
credentials: `DEEPSPACE_E2E_ENABLED=1`, storage state or token, base URL, and
tenant id. The suite verifies durable runtime reload, Library reachability, and
the private provider-health UI. Never run it against production by default.

## Local evidence recorded on 2026-09-23

The local isolated stack passed API readiness. The sandbox executor and browser
renderer profiles were started with their bearer tokens and passed bounded
smoke tests. The local voice agent registered with LiveKit after the local
agent/server credential mismatch was corrected. The complete backend suite,
complete frontend suite, TypeScript check, ESLint check, production frontend
build, and focused retention workflow all passed.

An authenticated local browser-level DeepSpace voice smoke now passes with a
disposable account, HTTPS/WSS, Chromium fake-microphone input, and granted
browser permission. The browser received a 200 voice token, connected through
the LiveKit WSS route, activated STT, and completed a local TTS audio check.
A physical microphone/device test and an approved external staging/VPS target
remain deployment proof gates. These checks do not change the DeepSpace chat or
queue contract.
