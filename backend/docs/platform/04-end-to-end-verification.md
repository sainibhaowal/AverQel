# 04. Current end-to-end verification

This is the current verification record for the Documents Hub and related
runtime changes. It supplements the reusable commands in
[`03-testing.md`](03-testing.md).

## Browser coverage

`frontend/e2e/documents-hub-workflows.spec.ts` covers:

1. loading and filtering quarantined documents;
2. expanding organization controls and reading webhook delivery history;
3. creating an expiring share link and resolving it through the share view;
4. running a grounded document action, opening citation page preview, and
   changing preview zoom.

The complete local Playwright run also covers DeepSpace budget metrics,
durable runtime controls, Library layout reachability, and the homepage.

Result on 2026-09-27: **10 passed, 0 skipped**.

The Documents Hub workflow file uses deterministic browser API fixtures so it
does not mutate a real tenant. This is browser contract coverage, not a claim
that fixture-backed tests replace live staging validation. Backend integration
tests cover tenant isolation, permissions, persistence, ingestion, OCR,
webhooks, recovery, and API behavior against the test services.

## Frontend checks

```bash
cd frontend
pnpm test -- --run
pnpm exec playwright test --workers=1 --timeout=60000
pnpm build
```

Current local result:

- Vitest: 88 files, 325 tests passed.
- Playwright: 10 passed, 0 skipped.
- Production build: passed, including dashboard, share, plan, storage, and
  document routes.

## Static quality gates

The final local quality pass on 2026-09-27 also passed:

```bash
cd backend
./.venv/bin/ruff check app tests
./.venv/bin/ruff format --check app tests
./.venv/bin/mypy app
python3 -m compileall -q app
cd ../frontend
pnpm lint
pnpm exec tsc --noEmit
```

- Ruff: clean; 615 Python files already formatted.
- mypy: no issues in 385 source files.
- ESLint and TypeScript: clean.
- Python compilation and `git diff --check`: clean.

The mypy configuration keeps a narrow, explicit override only for dynamic
SQLAlchemy/Celery integration boundaries; it does not disable checking for
the application package as a whole.

## Backend checks

```bash
cd backend
./.venv/bin/pytest -q --disable-warnings
./.venv/bin/pytest -q -n0 --disable-warnings
python3 -m compileall -q app
```

The full serial backend run passed on 2026-09-27. A parallel xdist run can
expose shared-resource contention in test environments that reuse the same
database or service namespace; use isolated worker databases/namespaces for
parallel CI. A serial green run is the deterministic fallback for diagnosis,
not a reason to weaken application assertions.

## Migration and container checks

```bash
cd backend
alembic upgrade head
alembic current
docker compose -f docker-compose.yml --env-file .env.localprod \
  up -d --build --remove-orphans
```

The current Documents Hub migration chain ends at
`20261009_0001_document_webhook_deliveries`. Verify health after rebuilding:

```bash
curl -fsS http://127.0.0.1:1000/api/v1/health/live
curl -fsS http://127.0.0.1:1000/api/v1/health/ready
```

Do not run application tests from an API image that intentionally excludes
`backend/tests`; run pytest from the repository checkout or a dedicated test
image containing the test tree.

## Release interpretation

“Passed locally” means the checked-out code and its disposable test services
passed. Production readiness additionally requires migration execution,
tenant-isolation checks, real object storage, worker health, OCR/malware
scanner availability, external provider credentials, and authenticated
staging browser validation. No test fixture should be described as external
production proof.
