# VPS deployment workflow

## Source and image selection

The manual deployment workflow accepts runs from `main` only. It records the
exact commit SHA, checks that it is the current `main` head before building,
and checks again after image publication before connecting to the VPS. If
`main` moved during a long build, the workflow stops and requires a fresh run.

GitHub builds, tests, scans, signs, and publishes the API, worker, and frontend
images with the selected commit SHA. The VPS pulls those same SHA-tagged images
and the Compose file from that commit. Local uncommitted changes and commits
that have not reached `main` are not part of the deployment.

The workflow sends a temporary copy of the checked-out Compose file to the
VPS for the deployment. `/opt/averqel/backend/docker-compose.prod.yml` on the
VPS may therefore lag behind the checked-in file. Do not use that on-disk copy
to determine which Compose configuration was used for the most recent
workflow run.

## Readiness, rollback, and cleanup

Compose waits for the API and frontend health checks. The workflow also checks
the running frontend image ID and metadata, API readiness/version, and public
API/frontend version and SHA. If deployment fails, it attempts to restore the
previous image versions when their metadata is available. Orphan containers
and unused AverQel image tags are removed only after health checks pass. The
cleanup is scoped to AverQel; it does not run Docker system, builder, image, or
volume prune commands and does not remove PostgreSQL, Redis, MinIO, or runtime
data volumes.

## Availability limitation

The deployment currently updates fixed-name Compose services in place. Docker
Compose replaces the old API and frontend containers before the post-deploy
checks complete. Health checks and rollback improve failure detection and
recovery, but they do not guarantee uninterrupted requests.

The public gateway is managed separately at `/opt/gateway` on the VPS. Its
current Caddy configuration routes to the fixed `averqel-api` and
`averqel-frontend` container names. A no-downtime blue/green deployment needs
an approved gateway switch/drain hook, parallel API/frontend slots, and
backward-compatible database migrations while both API versions run. Do not
describe the current workflow as zero-downtime.
