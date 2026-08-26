# LiveKit build provenance

The bundled `livekit-server` binary is built from the signed upstream
`livekit/livekit` release `v1.13.5`.

Build inputs:

- Go `1.26.6`
- `golang.org/x/mod` overridden to `v0.40.0` to include the current security
  fix required by the release-image vulnerability gate
- Linux `amd64`
- `CGO_ENABLED=0`

The upstream release archive was verified against its published SHA-256 before
building. The resulting binary was scanned with Trivy for HIGH and CRITICAL
vulnerabilities; the LiveKit binary reported zero findings.

To reproduce the build, download the source archive for `v1.13.5`, verify its
published checksum, then run:

```bash
go mod edit -require=golang.org/x/mod@v0.40.0
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
  go build -buildvcs=false -a -o livekit-server ./cmd/server
```

The repository also keeps `livekit.tar.gz` for the standalone LiveKit image.
It contains the same binary and the upstream license file.
