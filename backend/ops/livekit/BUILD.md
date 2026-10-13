# LiveKit build provenance

The API and worker images include the checked-in `livekit-server` binary. It is
built from the signed upstream `livekit/livekit` release `v1.13.9` and compiled
with Go `1.27.2` for Linux `amd64` with `CGO_ENABLED=0`.

The build uses `golang.org/x/net v0.60.0` to include the upstream security fix
that was not yet present in LiveKit's release dependency set. The Go module
download is checked by Go's public checksum database. The compiler image is
pinned by digest in `rebuild.sh`.

## Rebuild the checked-in artifacts

From the repository root, run:

```bash
./backend/ops/livekit/rebuild.sh
```

The script builds the binary, verifies its reported LiveKit version and
embedded Go module versions, and regenerates both `livekit-server` and the
`livekit.tar.gz` archive. It requires Docker and network access to the Go module
proxy.

The archive contains the same binary and the upstream license. It is kept in
sync with the checked-in binary for deployments that consume the archive
directly.

## CI verification

The VPS image workflow passes a unique run ID as `APT_REFRESH_ID` when building
the backend base image. This reruns the Debian package refresh even when
BuildKit has cached an earlier apt layer. It also checks the LiveKit version in
both backend images and uses Trivy `0.75.0` to scan the API, worker, and
frontend images for fixed HIGH and CRITICAL vulnerabilities. The scan gate
remains enabled; update the source, dependencies, or toolchain and rebuild the
artifacts when a new finding is reported.
