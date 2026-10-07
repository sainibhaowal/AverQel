# AverQel coding-agent instructions

This file is the shared project policy for coding agents. The detailed
plan-first, critical-review, test, documentation, and pre-push standards are in
[`AGENT_ENGINEERING_STANDARD.md`](AGENT_ENGINEERING_STANDARD.md). Read that
standard before implementation work, plus any more-specific instructions in
the working directory.

## Protect the working tree and running systems

- Before editing, inspect `git status` and the relevant diff. Preserve existing
  user changes, including untracked files. Do not reset, clean, stash, or
  overwrite work you did not create.
- Keep changes focused. Do not reformat unrelated files or run whole-repository
  format commands as a shortcut. In particular, `pnpm --dir frontend format`
  writes across the frontend.
- Before coding, present a plan that identifies the goal, current behavior,
  exact affected paths and interfaces, risks/non-break requirements, tests,
  and docs. Then proceed without waiting for routine approval. See the standard
  for the full planning and critical-review checklist.
- Never point tests at active development, staging, or production services.
  Database-backed backend tests must run through
  `./backend/scripts/test-isolated.sh`; direct database tests are designed to
  fail closed. The runner creates disposable private services and removes its
  own test containers when it exits.
- Database-free backend tests may run from `backend/` with
  `pytest -m unit_no_db`. Frontend browser tests use `pnpm --dir frontend e2e`;
  external browser targets require an explicitly disposable target and the
  documented opt-in in `backend/docs/security/isolated-test-runs.md`.
- Do not reset or migrate an active database, flush active Redis or object
  storage, restart/reload active services, deploy, or trigger a release unless
  the user explicitly asks for that operation in the current task.
- Do not commit, push, publish, or create a release unless explicitly asked.
  Do not expose secrets in output, logs, prompts, or generated files.

## Project boundaries

- `backend/` is the AverQel server. `frontend/` is the shared Next.js web app.
  `applications/desktop/` packages them in one Electron shell.
- NeoSIS is a separately maintained repository. Desktop builds bundle a pinned
  NeoSIS runtime into the Electron package; do not merge its source or its
  independent Electron application into AverQel. The release workflow checks
  out NeoSIS separately and records the exact source commit.
- The manual desktop release builds Linux `.deb` and Windows `.exe` packages.
  It does not deploy the VPS. VPS deployment is a separate manual workflow for
  AverQel's server services.
- Preserve tenant isolation, authentication and authorization boundaries,
  encrypted credentials, API compatibility, and existing security controls.
  Treat migrations, data deletion, and changes to release/deploy workflows as
  high-impact work and inspect their full effects before making them.

## Implementation and verification

- Read the relevant code, tests, and documentation before changing behavior.
  Every changed behavior or logic path needs appropriate focused tests. Review
  documentation impact on every implementation and update applicable docs in
  the same change. Use `production-change` for every implementation and
  `documentation-impact` after it.
- Run the checks that cover the changed paths. Use the current commands in
  `CONTRIBUTING.md`, `README.md`, and `backend/docs/platform/03-testing.md`.
  The pull-request workflow is defined in `.github/workflows/ci.yml`.
- Before a user-authorized push, use the `quality-gates` skill and run the full
  pre-commit and workflow validation required by the standard. After pushing,
  inspect CI for that exact commit and fix required failures.
- Never describe checks as passing unless they were run and passed. Report
  failures, skipped tests, checks not run, and any environmental limits
  explicitly. Investigate unexpected skips; do not hide them or remove
  assertions merely to make a run green.
- Review `git diff` after tools that can modify files. Stage or report only the
  changes relevant to the task; preserve unrelated work already in the tree.
- Explain what changed and give the exact verification evidence in the final
  update. Do not claim that local tests prove a deployment is healthy.
- Use `safe-testing` for test selection and isolation, `quality-gates` before
  readiness or push reports, and `desktop-release` for desktop package or
  release workflow work.
