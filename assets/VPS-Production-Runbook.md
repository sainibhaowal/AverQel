# Archived VPS production runbook

> **Retired:** this document described direct VPS source updates and manual
> service rebuilds. It is not the current deployment procedure.

Production deployment now uses the protected manual GitHub Actions workflow:
[Deploy - Manual Docker Build and VPS](../.github/workflows/deploy-vps.yml).
The workflow builds and tests immutable images from the selected `main`
commit, runs release checks, and deploys through the configured operator
credentials. See the [root release guide](../README.md#releases-and-deployment),
[release handoff](../backend/docs/release/01-end-to-end-handoff.md), and
[current release index](../backend/docs/release/03-current-worktree-change-index.md)
for evidence requirements and current migration status.

This archived file intentionally contains no VPS address, login, environment
file values, direct source synchronization commands, or destructive cleanup
steps. Do not restore those from an old checkout or copied runbook.
