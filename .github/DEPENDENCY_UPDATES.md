# Dependency update workflow

Dependency updates are intentionally consolidated into one pull request:

- Title: `chore(deps): update all dependencies`
- Label: `dependencies`
- Maximum open dependency PRs: one
- Managers: Python, frontend/desktop npm, Dockerfiles, and GitHub Actions
- CI: the normal `CI - Mandatory Quality Gates` workflow runs once for that PR

The workflow requires a `RENOVATE_TOKEN` repository secret. Use a dedicated
GitHub App token or fine-grained token that can read the repository, create a
branch, and create/update pull requests. Do not use a personal password or
place the token in a file.

Existing Dependabot pull requests are historical and are not automatically
deleted. Close those old PRs after this workflow creates the grouped update PR.
