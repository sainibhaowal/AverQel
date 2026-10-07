# 03. Backend test system

The backend test suite is split by dependency. Tests marked `unit_no_db` must
not require PostgreSQL, Redis, MinIO, network access, or application database
fixtures. Database-backed tests run in disposable PostgreSQL, Redis, and MinIO
services that are private to one test run. Each xdist worker gets its own
database. Integration tests are parallel-safe by default; only E2E tests
remain serialized until their object-storage namespaces are isolated.

Unit tests without database fixtures or known database-session imports are
conservatively classified as `unit_no_db` during collection. A unit module
that needs database access can opt out explicitly with
`pytestmark = pytest.mark.db`.

## Database lifecycle

The test run creates a fresh schema template by applying the checkout's
Alembic migrations to its disposable PostgreSQL service. It does not inspect
or copy schema/data from the active development database. Each worker creates
its own database with PostgreSQL's native `TEMPLATE` operation.

Ordinary database tests run inside one outer transaction per test and roll it
back in teardown; application commits are isolated with savepoints. Tests
that intentionally require independent committed state use the explicit
`db_commit` marker and receive one after-test cleanup. E2E tests use the same
cleanup path until their object-storage namespaces are isolated. The database
was created clean for the worker, so a second pre-test `TRUNCATE` is
unnecessary. A failed test is still cleaned before the next test; an interrupted
run is reset when the next session creates the worker database.

Database-backed tests fail closed when run directly in a normal shell. Their
fixtures reset databases and flush Redis, so run them only through
`./backend/scripts/test-isolated.sh`. Bootstrap failures are fatal; tests never
fall back to the development stack. The isolated stack has no network
interface, publishes no ports, stores data only in temporary container
storage, and is removed when the command exits.

## Commands

Run the database-free unit selection directly from `backend`:

```bash
cd /home/ravi/Projects/AverQel/backend
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 pytest -o cache_dir=/tmp/averqel-pytest-cache \
  tests/unit -m unit_no_db -n auto
```

Run database-backed tests from the repository root through the disposable
stack. Pytest arguments are passed through:

```bash
./backend/scripts/test-isolated.sh tests/unit
./backend/scripts/test-isolated.sh tests/integration -n 4
./backend/scripts/test-isolated.sh tests/unit tests/integration tests/security tests/e2e -n 4
```

Coverage is measured against the application source, not test files:

```bash
./backend/scripts/test-isolated.sh --cov=app --cov-report=term-missing
```

For the production paths changed most often in DeepSpace, run the focused
regression set before a full suite:

```bash
./backend/scripts/test-isolated.sh -q \
  tests/unit/test_auth_security.py \
  tests/unit/test_deepspace_chat_service.py \
  tests/unit/test_deepspace_runtime.py \
  tests/unit/test_deepspace_run_events.py \
  tests/unit/test_deepspace_task_loop.py \
  tests/unit/test_deepspace_library_storage.py \
  tests/unit/test_deepspace_library_uploads.py \
  tests/integration/test_mcp_api.py \
  tests/unit/test_provider_selection_service.py
```

Coverage is expected to grow through behavior-level tests. Do not exclude
uncovered application code or add tests that only execute lines without
asserting behavior. New or changed production paths must include focused
tests in the same change; the repository-wide percentage is a trend signal,
while critical-path regressions are release blockers.

The worker limit can be tuned after measurement:

```bash
AKS_TEST_XDIST_MAX_WORKERS=4 ./backend/scripts/test-isolated.sh tests/unit -n auto
```

Do not use `-n 0` for normal validation; it explicitly disables parallel
execution.

The Documents Hub browser workflows are covered by:

```bash
pnpm --dir frontend exec playwright test e2e/documents-hub-workflows.spec.ts --workers=1
pnpm --dir frontend exec playwright test --workers=1 --timeout=60000
```

The dedicated workflow file covers quarantine review, webhook delivery
history, expiring share links, citation page preview, and zoom. The full
local run also covers DeepSpace runtime, budget metrics, Library layout, and
homepage behavior. It completed with 10 passed and 0 skipped on 2026-09-27.

The production API image intentionally excludes `backend/tests`. The isolated
test runner builds a separate image and mounts the test checkout read-only; it
does not modify or restart the API image or active containers.

## DeepSpace release-focused checks

For changes to the durable runtime, queue, clarification resume, provider
routing, or webpage research path, run the focused checks before the full
suite:

```bash
./backend/scripts/test-isolated.sh -q tests/unit/test_deepspace_chat_service.py
./backend/scripts/test-isolated.sh -q \
  tests/unit/test_deepspace_runtime.py tests/unit/test_deepspace_run_events.py
./backend/scripts/test-isolated.sh -q \
  tests/unit/test_deepspace_tool_profiles.py tests/unit/test_provider_context_transport.py
```

The webpage research acceptance path proves the full sequence
`web_search -> url_read -> bounded source text -> citation`. A search-result
snippet alone is not an acceptable page-fetch test. The focused coverage also
checks direct HTTPS URL routing, private-target rejection, and optional
JavaScript-shell rendering.

The current workspace also contains new migrations for queued turns, request
metrics, runtime cascades, and context summaries. A release test must apply
the full Alembic history to a fresh database and upgrade an existing database
before worker startup is considered safe.
