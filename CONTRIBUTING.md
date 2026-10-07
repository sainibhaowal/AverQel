# Contributing to AverQel

Thank you for improving AverQel. Contributions must preserve tenant isolation,
credential privacy, reliable document processing, and the protected production
delivery path.

Agent-assisted work follows the repository's
[`AGENTS.md`](AGENTS.md) and detailed
[`AGENT_ENGINEERING_STANDARD.md`](AGENT_ENGINEERING_STANDARD.md). The standard
defines plan-first implementation, critical review, required tests,
documentation review, safe test isolation, and pre-push checks.

## Before changing code

1. Create a branch from the latest `main`:

   ```bash
   git switch main
   git pull --ff-only origin main
   git switch -c feat/short-description
   ```

2. Use a descriptive branch prefix such as `feat/`, `fix/`, `docs/`,
   `chore/`, or `security/`.
3. Read the relevant component guide and identify the tests that cover the
   change.
4. Never commit `.env*` files, tokens, private keys, model files, build
   outputs, `node_modules`, `.venv`, or `__pycache__` files.

## Plan, tests, and documentation

- Before implementation, inspect the existing behavior and working tree, then
  write a plan that names the goal, current state, affected files and
  interfaces, risks, non-break requirements, tests, and documentation. For
  routine changes, proceed after presenting the plan; it is not an approval
  gate.
- Add behavior-focused tests for new or changed logic and regression coverage
  for bug fixes. Choose unit, component, API/integration, migration, browser,
  or packaging tests according to the behavior being changed.
- Review documentation impact on every change. Update user help, API,
  configuration, security, testing, operator, or release docs in the same
  change when those details change. If no documentation edit is needed, record
  the reason in the completion report.
- Never use active databases or services for tests. Follow
  [`backend/docs/platform/03-testing.md`](backend/docs/platform/03-testing.md)
  and [`backend/docs/security/isolated-test-runs.md`](backend/docs/security/isolated-test-runs.md).

## Contribution terms

By submitting a contribution, you confirm that you have the right to submit
it and agree that it may be distributed under the [Apache License 2.0](LICENSE).
Do not submit code, documentation, media, or dependencies copied from a source
whose license is incompatible with Apache-2.0. Preserve required third-party
notices and identify material license changes in the pull request.

## Development rules

- Keep API changes tenant-scoped and authenticated.
- Keep OAuth secrets encrypted and out of logs, browser payloads, and prompts.
- Treat destructive actions as approval-gated operations.
- Preserve existing API contracts unless the pull request documents a
  deliberate migration.
- Update tests and documentation with behavior changes.
- Treat dependency upgrades as security-sensitive changes: update the lockfile,
  explain compatibility impact, and run the applicable audit and test checks.
- Do not edit VPS-owned files from the repository; production configuration
  belongs in `/opt/averqel/backend/.env.vps` and related operator-managed paths.

## Local verification

Run the smallest relevant checks while iterating, then run the complete
applicable suite before opening the pull request. The CI workflow decides
whether backend, frontend, or both suites apply based on the changed paths.

```bash
pnpm --dir frontend lint
pnpm --dir frontend test
pnpm --dir frontend build

cd backend
ruff check .
black --check .
mypy .
pytest -q -m unit_no_db --dist=loadgroup
```

## Pull requests

- Do not push directly to protected `main`; submit a pull request from your
  working branch.
- Use a title such as `feat: add provider health summary`, `fix: prevent ...`,
  or `docs: explain ...`.
- Describe the user-visible behavior, implementation, tests, migrations, and
  operational impact.
- Include screenshots or logs for UI and workflow changes when useful.
- Keep unrelated formatting, generated files, and dependency updates out of
  the change.
- Resolve all review conversations and wait for the required `CI Passed`
  check.

Install `pre-commit` and both repository Git hooks once after cloning:

```bash
python -m pip install pre-commit
pre-commit install
bash .github/scripts/install-pre-push-hook.sh
```

The pre-push hook requires `pre-commit` plus either Docker or a local
Actionlint installation. Docker runs the pinned Actionlint image when no local
binary is available.

The hook checks each pushed commit in a temporary detached worktree. It runs
the complete pre-commit suite and Actionlint against every workflow file. The
configured Ruff, Black, whitespace, and EOF formatters can modify files, so the
isolated hook keeps those edits out of the active checkout and blocks the push
if corrections need to be committed. Run applicable tests and quality gates
after fixes, inspect the complete diff and staged file list, and do not bypass
the hook. CI also runs Actionlint for every pull request, and the workflow lint
job is included in the required `CI Passed` result. After a push, inspect the
Actions results for that exact commit and resolve required failures before
merge.

Only reviewed pull requests may enter protected `main`. Release and VPS
deployment workflows are intentionally manual and are not triggered by an
ordinary pull request merge.

## Commit style

Use an imperative Conventional Commit style:

```text
feat(scope): add a user-visible capability
fix(scope): correct an observable failure
docs(scope): clarify an operational procedure
chore(scope): maintain tooling without product behavior changes
```

Breaking changes must be documented in the commit body with `BREAKING CHANGE:`
so semantic release calculation can identify them.
