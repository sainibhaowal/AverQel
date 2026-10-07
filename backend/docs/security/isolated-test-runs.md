# Safe local test runs

Database-backed backend tests reset their test database and flush Redis between
tests. Run them only through the isolated runner:

```bash
./backend/scripts/test-isolated.sh
```

You can pass normal pytest arguments to run a smaller selection:

```bash
./backend/scripts/test-isolated.sh tests/integration/test_auth_flow.py
./backend/scripts/test-isolated.sh -m 'db and not e2e'
```

The runner builds a separate test image and starts PostgreSQL, Redis, MinIO,
and the test process in a shared Docker network namespace with networking
disabled. Their loopback ports are not published to the host. Database and
object-storage data live in temporary container storage, the checkout is
mounted read-only, and the test container has no Docker socket. All test
containers are removed at exit. If Docker is unavailable or setup fails, the
command stops instead of falling back to local services.

Running backend database tests directly with `pytest` now fails closed. Tests
marked `unit_no_db` can still run directly because they do not reset or connect
to test services:

```bash
cd backend
pytest -m unit_no_db
```

Frontend browser tests use a local Next server on loopback and send API proxy
requests to a closed loopback port. They never reuse an existing server or load
the frontend `.local` runtime environment. Run them with:

```bash
pnpm --dir frontend e2e
```

If port `3103` is already occupied, Playwright stops instead of attaching to
that process. External browser E2E requires both an explicit target and an
explicit opt-in, for example:

```bash
DEEPSPACE_E2E_ALLOW_EXTERNAL=1 \
DEEPSPACE_E2E_BASE_URL=https://your-disposable-test-host \
pnpm --dir frontend e2e
```

External runs can write to the configured target. Use only an environment
created for testing; do not provide production credentials or production URLs.
