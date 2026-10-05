# Archived VPS command book

> **Retired:** this older guide described direct SSH, source sync, and manual
> Compose deployment. Those steps are not the current release procedure.

Use the repository's protected manual workflow to build and deploy the exact
`main` commit: [Deploy - Manual Docker Build and VPS](../.github/workflows/deploy-vps.yml).
Read the [release handoff](../backend/docs/release/01-end-to-end-handoff.md)
and [current release index](../backend/docs/release/03-current-worktree-change-index.md)
for migrations, backups, deployment gates, and environment evidence.

Do not use the historical server address, root account, direct `git pull`,
`rsync --delete`, or image/volume prune commands from copies of the retired
guide. Production secrets and host details belong in the operator's secret
store, not in repository documentation.
