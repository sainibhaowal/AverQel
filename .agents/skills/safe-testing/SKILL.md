---
name: safe-testing
description: Choose and run AverQel backend, frontend, and browser tests without touching active databases or services. Use when selecting tests, running integration or end-to-end tests, or investigating skipped or failing tests.
---

# Safe testing workflow

1. Read `backend/docs/platform/03-testing.md` and
   `backend/docs/security/isolated-test-runs.md` for current isolation rules.
   Inspect the changed behavior and identify positive, boundary, negative,
   permission, and failure cases that need coverage.
2. Inspect the working tree. Do not reuse credentials, URLs, containers, or
   data from an active development, staging, or production environment.
3. Run database-free backend tests from `backend/` with
   `pytest -m unit_no_db`. Run database-backed tests only through the isolated
   runner from the repository root:

   ```bash
   ./backend/scripts/test-isolated.sh
   ```

   Pass normal pytest arguments to narrow a run, for example:

   ```bash
   ./backend/scripts/test-isolated.sh tests/integration/test_auth_flow.py
   ./backend/scripts/test-isolated.sh -m 'db and not e2e'
   ```

   The runner starts disposable, network-isolated PostgreSQL, Redis, and
   MinIO services. If Docker or setup is unavailable, stop and report the
   failure; never fall back to active local services.
4. Run frontend unit tests with `pnpm --dir frontend test`. Run browser E2E
   with `pnpm --dir frontend e2e`. The configured local E2E server uses
   loopback and stops if its port is already occupied; do not attach it to an
   existing server. External browser tests require an explicitly disposable
   target and the documented opt-in.
5. Add tests at the narrowest layer that proves the behavior. Use API,
   integration, migration, or browser E2E coverage when unit tests cannot
   verify the contract, persistence, security boundary, or critical user flow.
   Do not add tests that only execute code without asserting outcomes.
6. Record exact commands and pass/fail/skip counts. Investigate unexpected
   skips and failures. Never claim a full suite passed when only a subset ran,
   and do not remove assertions or skip markers just to obtain a green result.
   Platform or environment skips must have a documented reason and be reported.

Do not reset databases, flush shared services, run migrations against active
systems, or start/stop the regular application Compose stack as part of this
workflow.
