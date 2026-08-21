# AverQel - What You Do Every Day

> You are developer. You change code, push to GitHub, it becomes live on `144.91.118.196` by itself.
> VPS is `root@144.91.118.196` `/opt/averqel` - you don't SSH every time now.
> Secrets `VPS_HOST` `VPS_USER` `VPS_SSH_KEY` `GHCR_PAT` already added.

---

## Your Normal Day - 4 Steps

### Step 1 - Change code on your laptop

This is normal. You edit files in `backend/` or `frontend/` like always.

```bash
cd /home/ravi/Projects/AverQel
git pull --ff-only origin main
# now edit your files
```

### Step 2 - Auto check before commit (you do nothing)

**Installed: `.pre-commit-config.yaml:1` + `.git/hooks/pre-commit`**
Now when you run `git commit`, this runs **automatically** on your laptop before GitHub, before push:

* `backend/.venv/bin/ruff check . --fix` -> fixes lint
* `backend/.venv/bin/black .` -> fixes format
* `backend/.venv/bin/mypy .` -> type check
* `frontend pnpm lint` -> frontend lint

If it fixes files, commit is blocked with `files were modified by this hook` -> just do:
```bash
git add .
git commit -m "feat: ..."
```
again. No need to type those `ruff/black/mypy` commands manually every day.

`pnpm build`, `bandit`, `pytest`, `pip-audit` still run on GitHub `ci.yml:1` - you don't run them daily unless you want. If you want to test all gates manually before push:
```bash
cd backend && ./.venv/bin/pytest -q
cd ../frontend && pnpm build
```

### Step 3 - Push your work to GitHub

**Important - Write good commit message.** The system reads your message to decide version:

* You fixed a bug: `fix: ...` -> becomes `v1.0.0` -> `v1.0.1` (patch)
* You added a feature: `feat: ...` -> becomes `v1.0.1` -> `v1.1.0` (minor)
* You broke something old: `feat!: ...` -> becomes `v1.1.0` -> `v2.0.0` (major)
* Docs only: `docs: ...` -> no new version

Example:
```bash
cd /home/ravi/Projects/AverQel
git status --short
git add backend/app/your/file.py frontend/app/your/page.tsx
git commit -m "feat: add search filters"
git push origin main
```

After `git push origin main`:
* GitHub runs checks `ci.yml` - you see green check on your commit
* GitHub creates a **Pull Request** called `chore: release v1.1.0` - this is not live yet, just a preview with new version and notes

You can keep pushing more `feat:` / `fix:` to `main` - that same PR will update to `v1.1.0` -> `v1.1.1` etc.

### Step 4 - Make it live on VPS (when you are ready)

Go to **GitHub -> Pull requests** -> open `chore: release v1.1.0` -> click `Merge pull request` -> `Confirm merge`.

Then **without touching VPS**, this happens by itself:
1. GitHub creates tag `v1.1.0` and Release `AverQel v1.1.0`
2. Builds 3 private images `ghcr.io/sainibhaowal/averqel-api:v1.1.0` `averqel-worker:v1.1.0` `averqel-frontend:v1.1.0`
3. SSH to `144.91.118.196` does `git checkout v1.1.0` -> `docker pull` -> `docker up -d` -> deletes old images, keeps only `v1.1.0` -> checks health

Check it worked (on your laptop):
```bash
curl -fsS https://averqel.com/api/v1/health/ready | python3 -m json.tool
# should show "version": "v1.1.0"
```
And footer on website shows `v1.1.0`.

**That's your whole day: change -> check -> commit with `feat:/fix:` -> push main -> merge Release PR when ready -> live.**

---

## What you DON'T do anymore

* Don't run `ssh root@144.91.118.196` + `git pull origin main` + `docker compose up -d --build` - pipeline does it
* Don't run `docker image prune` manually - pipeline deletes old builds keeping only active version

---

## If you need hotfix without Release PR

If live is broken and you need `v1.0.1` right now without waiting for PR:

```bash
git tag v1.0.1 -m "hotfix"
git push origin v1.0.1
# -> directly builds and deploys v1.0.1 to VPS
```

---

## If you changed desktop app only

Most `v*` pushes don't need desktop. Only when you change `applications/desktop`:

```bash
git tag desktop-v1.0.0 -m "desktop"
git push origin desktop-v1.0.0
# -> builds deb/msi/exe only, VPS not touched
```

---

## If deploy failed - check

* GitHub -> Actions -> `Backend/Web Release - v*` - see which step failed (gates, build, deploy)
* Only then SSH to VPS:
```bash
ssh root@144.91.118.196
cd /opt/averqel
docker compose --env-file backend/.env.vps -f backend/docker-compose.prod.yml ps
docker compose --env-file backend/.env.vps -f backend/docker-compose.prod.yml logs --tail=100 api
```
