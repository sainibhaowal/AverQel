# Archived Docker command notes

> **Retired:** the commands formerly in this file described older Compose
> layouts and included cleanup steps that are not appropriate as routine
> deployment actions.

For local development, follow the [repository overview](../README.md#local-development)
and [backend documentation index](../backend/docs/README.md). For production,
use the protected [manual Docker/VPS deployment workflow](../.github/workflows/deploy-vps.yml)
and its linked release, backup, and verification guides.

Confirm the selected environment and configuration before running Compose
commands. Never use production environment files for local development, and
do not run `down -v`, broad prune commands, `--remove-orphans`, or
`rsync --delete` as routine deployment steps.
