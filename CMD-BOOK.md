# AverQel contributor and release quick reference

This page is a short command and workflow guide. It follows the repository's
current protected-branch, manual-release, and manual-deployment setup. The
canonical contributor rules are in [`CONTRIBUTING.md`](CONTRIBUTING.md); the
release and deployment details are in [`README.md`](README.md) and the linked
GitHub Actions workflows.

## Work on a change

Start from an up-to-date checkout, create a branch, make the change, and run
the relevant checks:

```bash
git switch main
git pull --ff-only origin main
git switch -c docs/short-description

# Run checks that match the files you changed.
pnpm --dir frontend lint
pnpm --dir frontend test
pnpm --dir frontend exec tsc --noEmit
pnpm --dir frontend build
```

For backend changes, use the project virtual environment from `backend/`:

```bash
cd backend
./.venv/bin/ruff check app tests
./.venv/bin/pytest -q
```

Do not run formatting commands that rewrite unrelated files. Review
`git status --short` and the diff, then commit only the intended files:

```bash
git status --short
git diff --check
git diff
git add path/to/changed-file
git commit -m "docs: explain a product workflow"
git push -u origin docs/short-description
```

Open a pull request and wait for required review and CI. Do not push directly
to protected `main`.

## Publish a desktop release

The **Release - Manual SemVer and Desktop** workflow is run manually from
protected `main`. It selects or calculates a canonical `vMAJOR.MINOR.PATCH`
version, builds desktop packages, and publishes the GitHub release. It does
not deploy the web application to the VPS.

Use GitHub **Actions → Release - Manual SemVer and Desktop → Run workflow**.
Leave the version input empty to calculate the next version, or enter an exact
canonical version when the release process calls for one. Review the generated
release assets and manifest after the workflow completes.

## Deploy the web application

The **Deploy - Manual Docker Build and VPS** workflow is separate and also
starts manually from `main`. It builds and tests images from the selected main
commit, publishes immutable images, then deploys them to the configured VPS.
The workflow checks migration and service readiness and has rollback handling;
those checks do not replace authenticated staging or feature-specific smoke
tests.

Run it only after the intended commit is on `main`, required release gates are
recorded, and production configuration and backups are ready. Use GitHub
**Actions → Deploy - Manual Docker Build and VPS → Run workflow**. Confirm the
source commit shown by the run, inspect every job, and verify the resulting
release version and health endpoints. Never copy server addresses, credentials,
or private environment values into this repository or public issue.

For the full deployment procedure and evidence requirements, use the
[release handoff](backend/docs/release/01-end-to-end-handoff.md),
[production verification guide](backend/docs/release/02-production-e2e-verification.md),
and [current release index](backend/docs/release/03-current-worktree-change-index.md).

## Desktop development

The desktop client uses the shared frontend and normally opens the local web
app with:

```bash
pnpm electron dev
```

To explicitly use the local HTTPS reverse proxy and its API, set both values:

```bash
ELECTRON_START_URL=https://averqel.localhost \
NEXT_PUBLIC_API_URL=https://averqel.localhost/api/v1 \
pnpm electron dev
```

Desktop packaging instructions are in
[`applications/desktop/README.md`](applications/desktop/README.md).
