# Backend test system

The backend test suite is split by dependency. Tests marked `unit_no_db` must
not require PostgreSQL, Redis, MinIO, network access, or application database
fixtures. Database-backed tests run against an isolated PostgreSQL database per
xdist worker. Integration tests are parallel-safe by default; only E2E tests
remain serialized until their object-storage namespaces are isolated.

Unit tests without database fixtures or known database-session imports are
conservatively classified as `unit_no_db` during collection. A unit module
that needs database access can opt out explicitly with
`pytestmark = pytest.mark.db`.

## Database lifecycle

The first database-backed worker creates a migrated template database. The
template is rebuilt only when the source `alembic_version` changes. Each worker
then creates its own database with PostgreSQL's native `TEMPLATE` operation.
This avoids repeating `pg_dump`, restore, and Alembic migration work for every
worker.

Ordinary database tests run inside one outer transaction per test and roll it
back in teardown; application commits are isolated with savepoints. Tests
that intentionally require independent committed state use the explicit
`db_commit` marker and receive one after-test cleanup. E2E tests use the same
cleanup path until their object-storage namespaces are isolated. The database
was created clean for the worker, so a second pre-test `TRUNCATE` is
unnecessary. A failed test is still cleaned before the next test; an interrupted
run is reset when the next session creates the worker database.

Bootstrap failures are fatal by default so a partially initialized database
cannot produce a false-green test run. For local diagnosis only, an explicit
`AKS_TEST_ALLOW_BOOTSTRAP_SKIP=true` can restore the old skip behavior.

## Commands

Run commands from `backend` with the project virtual environment:

```bash
cd /home/ravi/Projects/AverQel/backend
source .venv/bin/activate
pytest tests/unit -m unit_no_db -n auto
pytest tests/unit -n auto
pytest tests/integration -n 4
pytest tests/unit tests/integration tests/security tests/e2e -n 4
```

Coverage is measured against the application source, not test files:

```bash
pytest --cov=app --cov-report=term-missing --cov-report=json
```

For the production paths changed most often in DeepSpace, run the focused
regression set before a full suite:

```bash
pytest -q \
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
AKS_TEST_XDIST_MAX_WORKERS=4 pytest tests/unit -n auto
```

Do not use `-n 0` for normal validation; it explicitly disables parallel
execution.
