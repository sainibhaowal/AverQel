---
name: desktop-release
description: Build, inspect, or troubleshoot AverQel desktop releases containing the shared Electron shell and AverQel frontend. Use for .deb, .exe, release workflow, or release-manifest tasks.
---

# Desktop release workflow

1. Read `AGENT_ENGINEERING_STANDARD.md`, use `production-change` and
   `quality-gates`, and read `applications/desktop/README.md`,
   `.github/workflows/release-semantic.yml`, and the release-related sections
   of `README.md`. Inspect the current worktree and preserve unrelated changes.
2. The release workflow checks out AverQel at the selected protected `main`
   commit, builds the production frontend, and packages only the AverQel
   desktop shell and frontend. Do not add separately maintained applications
   to the AverQel package without an explicit product decision.
3. For a local Linux package, use the documented local build sequence:

   ```bash
   BUILD_TARGET=desktop pnpm --dir frontend build
   pnpm --dir applications/desktop build:linux
   ```

   The Linux build emits an AverQel `.deb` package.
4. The release workflow is manually dispatched from protected `main` and
   builds Linux `.deb` and Windows `.exe` packages. It publishes release assets
   and metadata to GitHub; desktop download metadata is consumed by the website.
   macOS is not in the release matrix. VPS deployment is a separate manual
   workflow and must not be triggered as part of a desktop release.
5. Before any release, verify the selected AverQel commit, generated package
   names, checksums, and release manifest. Trigger a release,
   publish, or deployment only when the user explicitly requests that action.
6. If release or workflow source changes, update the relevant operator docs,
   validate every workflow with the pinned Actionlint image or a local
   Actionlint binary, run applicable tests and quality gates, and inspect the
   diff. CI runs this workflow lint for every pull request. Before any
   requested push, complete the isolated pre-push checklist in `quality-gates`.

Never infer that a package is complete from a successful frontend build alone.
Report the exact platform builds and artifact checks that were actually run.
