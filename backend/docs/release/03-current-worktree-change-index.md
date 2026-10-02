# 03. Current worktree change index

This index records the feature families updated in the current AverQel
worktree so release reviewers can find the detailed contract instead of
relying on a long file diff.

## Documents and ingestion

- Documents Hub organization, duplicates, versions, AI actions, sharing,
  comments, bulk operations, quality reports, previews, automation, webhooks,
  observability, and browser workflows: [`../library/07-documents-hub-workflows.md`](../library/07-documents-hub-workflows.md).
- Checkpoints, recovery, scanner behavior, OCR quality, page diagnostics, and
  operational triage: [`../library/08-ingestion-recovery-security-observability.md`](../library/08-ingestion-recovery-security-observability.md).
- Upload, extraction, storage, supported formats, and existing safety
  invariants: [`../library/05-documents-production.md`](../library/05-documents-production.md).
- OCR adapter and native-text/OCR boundary:
  [`../library/06-ingestion-ocr.md`](../library/06-ingestion-ocr.md).
- End-user Documents Hub behavior, before/now comparison, UI states, and
  complete lifecycle:
  [`../library/09-documents-hub-user-guide.md`](../library/09-documents-hub-user-guide.md).

## DeepSpace runtime and composer

- Composer device files, screenshots, clipboard paste, drag/drop, previews,
  Library persistence, and attachment IDs:
  [`../deepspace/09-composer-library-attachments.md`](../deepspace/09-composer-library-attachments.md).
- Durable queue, retries, checkpoints, context budgets, tool results,
  realtime events, and runtime transitions: the numbered documents in
  [`../deepspace/`](../deepspace/), especially `03`, `04`, `05`, `08`, and
  `09`.
- Provider-safe reasoning, model selection, MCP authorization, and low-latency
  behavior remain documented in `capabilities/`, `deepspace/`, and the
  provider platform pages. Raw private reasoning is not exposed to clients.

## Storage, plans, and platform safety

- Tenant storage allocation, quota reservations, archive lifecycle,
  protection leases, reconciliation, and restore safety:
  [`../storage/02-storage-retention-production-guide.md`](../storage/02-storage-retention-production-guide.md)
  and [`../storage/retention/README.md`](../storage/retention/README.md).
- Authentication, tenant context, OAuth, encrypted provider/webhook secrets,
  and permission boundaries: [`../platform/02-auth-oauth-login.md`](../platform/02-auth-oauth-login.md)
  and the security sections of the capability documents.
- Provider usage normalization, disabled-provider handling, operational
  metrics, and admin observability are covered by the platform and capability
  documents; metrics remain low-cardinality and content-free.

## Frontend and realtime UX

The current frontend changes preserve existing routes and add or refine:

- Documents Hub list, organization panel, detail inspector, OCR/read mode,
  technical fragments, preview, citation page navigation, and share view;
- DeepSpace composer attachment states, queue/reconnect state, Library drawer,
  model/reasoning controls, provider status, and responsive layouts;
- semantic light/dark tokens, centered controls, accessible names, restrained
  hover/active motion, and mobile-safe wrapping.

The source of truth is the frontend route/component code; the backend docs
describe its API and safety contract. Browser evidence is recorded in
[`../platform/04-end-to-end-verification.md`](../platform/04-end-to-end-verification.md).

## Migrations in scope

The current ordered Alembic graph has one head, `20261012_0007`, and includes
the runtime/storage, document organization, webhook, Smart Collection, and
collection-hardening revisions. Confirm the target database state and review
unique-index preconditions before applying it; never cherry-pick a feature
without its dependent migration.

## Verification evidence

Verification must be recorded against the exact checkout and test inputs.
Latest evidence available during this review:

- full backend pytest suite (`pytest -q -n 0`): completed successfully at 100%,
  exit code 0. Repository quiet mode suppressed numeric pass/skip counts;
- frontend Vitest: 92 files, 329 tests passed;
- frontend ESLint: 0 errors, 2 warnings; TypeScript check passed;
- frontend production build: passed;
- backend Ruff and Black: passed; mypy: no issues in 642 source files;
- Bandit: completed without medium-or-higher findings; existing `nosec`
  informational warnings were emitted;
- `git diff --check`: passed;
- latest local authenticated Playwright run: 10 passed, 0 failed, 0 skipped,
  using a dedicated local E2E admin account. This verifies the local checkout
  against the local API; it is not staging/production verification.

These local results do not replace staging verification with real credentials,
storage, workers, scanner, OCR, providers, and tenant data. The full backend
suite's exact pass/skip counts should be captured with a non-quiet pytest
reporter if a numerical breakdown is required.
