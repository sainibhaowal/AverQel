# DeepSpace private operations runbook

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

Confirm that the following current-worktree migrations are present in the
applied revision history:

- `20260916_0001_deepspace_queued_turns`
- `20260916_0002_deepspace_request_metrics`
- `20260917_0001_cascade_deepspace_runtime_and_snapshots`
- `20260918_0001_deepspace_context_summaries`

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

## Browser validation

Run authenticated Playwright only against a staging instance with short-lived
credentials: `DEEPSPACE_E2E_ENABLED=1`, storage state or token, base URL, and
tenant id. The suite verifies durable runtime reload, Library reachability, and
the private provider-health UI. Never run it against production by default.

## Local evidence recorded on 2026-09-17

The local isolated stack passed API readiness and the Chromium homepage E2E
smoke test. The full authenticated DeepSpace suite was intentionally not run
without a disposable staging identity and synthetic tenant data. This is a
safety boundary, not a product failure.
