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

# AverQel Production Docker Commands

This file explains the two supported Docker run modes for AverQel:

- local production-like run on your own machine
- real VPS production run on the server

The goal of this file is simple:

- tell you what each mode is for
- tell you when to use each command
- avoid duplicate command lists that look the same

## 1. First Understand The Two Modes

- http://host.docker.internal:1234/v1
  http://localhost:1234/v1

### 1.1 Local Production-Like

This mode is for your laptop or desktop.

What it is for:

- test the full stack locally with Docker
- run the same service layout as production
- verify builds, migrations, proxying, and health checks locally

What it is not for:

- it is not the real public deployment
- it is not full production hardening

Current local profile:

- env file: `backend/.env.localprod`
- compose file: `backend/docker-compose.prod.yml`
- domain: `localhost`
- app URL: `https://localhost`
- app env: `AKS_ENV=staging`
- local MinIO runs on HTTP
- local cookies are non-secure because this is a localhost workflow

### 1.2 Real VPS Production

This mode is for the real server.

What it is for:

- public deployment
- real domain and real TLS
- real production settings

Current VPS profile:

- env file: `backend/.env.vps`
- compose file: `backend/docker-compose.prod.yml`
- domain: `averqel.com`
- app env: `AKS_ENV=production`

## 2. Rules That Apply To Both Modes

- Run commands from: `/home/ravi/Projects/AverQel`
- The API container applies migrations automatically on startup with `alembic upgrade head`
- Use `--build` for normal rebuilds
- Use `--no-cache` only when Docker cache is clearly stale
- Run `docker image prune -f` and `docker builder prune -f` only after the deployment command succeeds
- Do not mix `backend/.env.localprod` and `backend/.env.vps`
- Do not run VPS commands on the laptop

## 3. Local Production-Like Workflow

```bash
cd applications/desktop
pnpm electron dev
```

Use this whole section only for your local machine.

### 3.1 What You Open Locally

- main app: `https://localhost`
- HTTP entrypoint: `http://localhost`
- expected behavior: HTTP redirects to HTTPS

### 3.2 Local Preflight Check

Use this before the first run or before a major rebuild.

What it checks:

- the local env file is present
- the provider key placeholder is not still left unresolved
- the compose file renders correctly with the local env

```bash
cd /home/ravi/Projects/AverQel

grep -n 'SET_REAL_PROVIDER_API_KEY_BEFORE_LOCAL_PROD_RUN' backend/.env.localprod || true
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.localprod config >/tmp/AverQel-localprod-config.out
```

If `grep` prints a line, fix `backend/.env.localprod` first.

### 3.3 Choose The Right Local Command

You do not run all commands below.
You choose one command based on what changed.

#### Case A: First Start Or After Full Cleanup

Use this when:

- you have never started the local stack before
- you ran a full reset
- you want everything rebuilt and started again

Command:

```bash
cd /home/ravi/Projects/AverQel
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --build --remove-orphans
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

What it affects:

- postgres
- redis
- minio
- inference
- api
- worker
- scheduler
- frontend
- caddy

#### Case B: Backend API-Only Change

Use this when you changed only API/backend app code and you do not need worker, scheduler, or frontend rebuilt immediately.

Command:

```bash
cd /home/ravi/Projects/AverQel
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --build api
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

What it affects:

- api only

```bash
docker builder prune -f
docker image prune -f
```

#### Case C: Worker Or Scheduler Change

Use this when you changed:

- Celery tasks
- background job logic
- scheduler logic

Command:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --build worker scheduler
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

```bash
docker builder prune -f
docker image prune -f
docker system prune -f
```

What it affects:

- worker
- scheduler

#### Case D: Frontend Change

Use this when you changed:

- Next.js pages
- UI components
- frontend-only logic

Command:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --build frontend caddy
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

What it affects:

- frontend
- caddy

#### Case E: Inference Change

Use this when you changed local inference or embedding/reranking runtime behavior.

Command:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --build inference
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

What it affects:

- inference

#### Case F: Broad Or Unclear Change

Use this when:

- both frontend and backend changed
- shared config changed
- Dockerfiles changed
- you are not sure what is affected

Command:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --build --remove-orphans
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

What it affects:

- the full stack

### 3.4 Local Restart Without Rebuild

Use this when code did not change and you only want containers restarted.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod restart
```

### 3.5 Local Stop Without Deleting Data

Use this when you want to stop the local stack but keep local Docker volumes.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod down --remove-orphans
```

### 3.6 Full Local Reset

Use this only when you intentionally want to delete local AverQel runtime state and start over.

What it removes:

- AverQel containers
- AverQel Docker volumes
- local DB state
- local Redis state
- local MinIO data
- runtime files under `runtime/backend`

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod down --volumes --remove-orphans
docker image prune -f
docker builder prune -f
rm -rf runtime/backend/*
```

Then start again with `Case A` from section `3.3`.

### 3.7 Local Health Checks

Use these after local startup.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
curl -I http://localhost
curl -k -I https://localhost
curl -ks https://localhost/api/v1/health/live
curl -ks https://localhost/api/v1/health/ready
```

Expected results:

- `http://localhost` returns `308 Permanent Redirect`
- `https://localhost` returns `200`
- both HTTPS health endpoints return `200`

### 3.8 Local Logs

Use these when something looks wrong locally.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod logs -f caddy
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod logs -f api
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod logs -f worker
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod logs -f scheduler
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod logs -f frontend
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod logs -f inference
```

### 3.9 Local Cleanup Of Old Images

Use this only after a successful local rebuild.

```bash
cd /home/ravi/Projects/AverQel
docker builder prune -f

2docker image prune -f
docker system prune -f
```

### 3.10 Local No-Cache Rebuild

Use this only when Docker cache is clearly wrong.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod build --no-cache
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod up -d --remove-orphans
docker compose -f backend/docker-compose.yml --env-file backend/.env.localprod ps
```

## 4. Real VPS Production Workflow

Use this whole section only on the VPS.

### 4.1 What VPS Production Means Here

This is the real public deployment.

It uses:

- `backend/docker-compose.prod.yml`
- `backend/.env.vps`
- real domain: `averqel.com`
- real production settings

### 4.2 VPS Preflight Check

Use this before the first VPS deployment or before a major redeploy.

What it checks:

- the VPS env file exists
- the provider API key placeholder is not still present
- the compose file renders correctly with the VPS env

```bash
cd /home/ravi/Projects/AverQel

grep -n 'SET_REAL_PROVIDER_API_KEY' backend/.env.vps || true
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps config >/tmp/AverQel-vps-config.out
```

Also confirm:

- ports `80` and `443` are open on the VPS firewall
- DNS still points to the VPS origin IP
- the VPS has the code version you want to run

### 4.3 VPS Deploy Command

Use this for the normal VPS deployment or redeploy.

Helper script:

```bash
cd /home/ravi/Projects/AverQel

bash backend/scripts/deploy_prod.sh
```

Direct compose command:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps up -d --build --remove-orphans
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps ps
```

### 4.4 VPS Restart Without Rebuild

Use this when code did not change and you only want to restart the running services.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps restart
```

### 4.5 VPS Stop Without Deleting Data

Use this when you need to stop the stack but keep persistent data.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps down --remove-orphans
```

### 4.6 VPS Health Checks

Use these after deployment on the VPS.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps ps
curl -I http://localhost
curl -k -I https://localhost
curl -ks https://localhost/api/v1/health/live
curl -ks https://localhost/api/v1/health/ready
```

### 4.7 VPS Logs

Use these when the VPS deployment looks wrong.

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f api
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f worker
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f scheduler
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f frontend
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f inference
```

### 4.8 VPS Cleanup Of Old Images

Use this only after a successful VPS rebuild when disk usage is growing.

```bash
cd /home/ravi/Projects/AverQel

docker image prune -f
docker builder prune -f
```

### 4.9 VPS Warning

Do not do a full volume reset on the VPS unless you intentionally want to destroy production data.

## 5. Very Short Cheat Sheet

### Local

- first start or after reset: use section `3.3` Case A
- backend-only change: use section `3.3` Case B or C
- frontend-only change: use section `3.3` Case D
- inference change: use section `3.3` Case E
- mixed or unclear change: use section `3.3` Case F

### VPS

- normal deploy: use section `4.3`
- restart only: use section `4.4`
- health check: use section `4.6`
- logs: use section `4.7`

### 2.2 VPS Preflight Check

Run this on the VPS before the first production start or any major redeploy:

```bash
cd /home/ravi/Projects/AverQel

grep -n 'SET_REAL_PROVIDER_API_KEY' backend/.env.vps || true
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps config >/tmp/AverQel-vps-config.out
```

If the `grep` command prints a line, fix `backend/.env.vps` first.

Also make sure:

- ports `80` and `443` are open on the VPS firewall
- the Cloudflare DNS record still points to the VPS origin IP
- the repo on the VPS contains the latest code you intend to run

### 2.3 First Production Start Or Normal Redeploy

Use the deploy helper from the repo root:

```bash
cd /home/ravi/Projects/AverQel

bash backend/scripts/deploy_prod.sh
```

This uses `backend/.env.vps` by default and runs:

- `docker compose ... pull || true`
- `docker compose ... up -d --build`
- `docker compose ... ps`

If you want to pass an explicit env file path:

```bash
cd /home/ravi/Projects/AverQel

bash backend/scripts/deploy_prod.sh /home/ravi/Projects/AverQel/backend/.env.vps
```

### 2.4 Direct Docker Commands On VPS

If you do not want to use the helper script, use the compose commands directly:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps up -d --build --remove-orphans
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps ps
```

### 2.5 Check Production Status On VPS

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps ps
```

Useful additional logs:

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f api
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f worker
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f scheduler
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f frontend
docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps logs -f inference
```

### 2.6 Restart Production Without Rebuild

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps restart
```

### 2.7 Stop Production But Keep Data

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps down --remove-orphans
```

### 2.8 VPS Health Checks

```bash
cd /home/ravi/Projects/AverQel

docker compose -f backend/docker-compose.prod.yml --env-file backend/.env.vps ps
curl -I http://localhost
curl -k -I https://localhost
curl -fsS http://localhost/api/v1/health/live
curl -fsS http://localhost/api/v1/health/ready
```

### 2.9 VPS Cleanup Of Old Build Cache

Use this after successful rebuilds if disk usage starts growing:

```bash
cd /home/ravi/Projects/AverQel

docker image prune -f
docker builder prune -f
```

Do not run full volume deletion on the VPS unless you intentionally want to destroy production data.

## 3. Important Note On Old Images

These commands intentionally use:

```bash
docker image prune -f
docker builder prune -f
```

This removes old dangling images and unused build cache so local storage does not keep growing after rebuilds.

It does not remove active images currently used by running containers.
