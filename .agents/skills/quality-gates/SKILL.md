---
name: quality-gates
description: Run and diagnose AverQel's applicable backend, frontend, formatting, type, security, test, documentation, and GitHub Actions checks. Use before reporting code changes ready or before any requested push.
---

# Quality-gate workflow

1. Read `AGENT_ENGINEERING_STANDARD.md`, `CONTRIBUTING.md`, the relevant
   component guide, and `.github/workflows/ci.yml`. Check changed paths and
   run every gate that applies to them.
2. Prefer read-only checks. The backend CI commands are defined in
   `.github/scripts/run-backend-gate.sh`. To execute every backend CI quality
   gate from the repository root, use:

   ```bash
   set -euo pipefail
   cd backend
   for gate in ruff black mypy bandit pip-audit safety pytest; do
     bash ../.github/scripts/run-backend-gate.sh "$gate"
   done
   ```

   The backend CI pytest gate covers `unit_no_db`. For database-backed tests,
   use `safe-testing` and `./backend/scripts/test-isolated.sh`; include the
   full suite when the change or requested release validation requires it.
3. For frontend changes, common local checks from the repository root are:

   ```bash
   pnpm --dir frontend lint
   pnpm --dir frontend test
   pnpm --dir frontend build
   pnpm --dir frontend audit --prod --audit-level high
   ```

   Run `pnpm --dir frontend e2e` when browser coverage applies. Do not use the
   project-wide `pnpm --dir frontend format` command for a targeted change; it
   writes across the frontend.
4. Ensure `pre-commit` and both repository hooks are installed before pushing:

   ```bash
   python -m pip install pre-commit
   pre-commit install
   bash .github/scripts/install-pre-push-hook.sh
   ```

   The hook runs the full configured pre-commit suite and Actionlint for every
   pushed commit inside a temporary detached worktree. Formatter changes stay
   out of the active checkout and block the push until corrected and committed.
   It requires Docker or a local Actionlint binary.
   If running checks manually, use a disposable worktree because pre-commit
   includes mutating formatters. Run all applicable tests and static gates after
   fixes, then inspect the complete diff and staged file list. Do not bypass the
   hook or push with an incomplete gate.
5. CI runs Actionlint on all workflow files for each pull request, and its
   result is part of the required `CI Passed` check. After a requested push,
   inspect GitHub Actions for that exact commit. Keep
   resolving required failures until they pass. A green result from a different
   SHA does not validate the pushed commit. Do not merge, publish, or deploy
   unless separately authorized.
6. Review documentation impact and update relevant docs. Verify changed
   Markdown links and commands against the repository. Report documentation
   changes or why none were needed.
7. Report exact commands and outcomes, including pass/fail/skip counts, CI
   commit SHA, gates not run, and environmental limits. Do not claim all checks
   are green unless the complete applicable set passed.
