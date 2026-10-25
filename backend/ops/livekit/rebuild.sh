#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$(mktemp -d)"
BUILDER_IMAGE="golang:1.27.3-bookworm@sha256:972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5"
trap 'rm -rf "$BUILD_DIR"' EXIT

docker run --rm --platform linux/amd64 \
  --volume "$BUILD_DIR:/out" \
  "$BUILDER_IMAGE" \
  bash -euo pipefail -c '
    test "$(go version)" = "go version go1.27.3 linux/amd64"
    export GOPROXY=https://proxy.golang.org,direct
    export GOSUMDB=sum.golang.org

    go mod download github.com/livekit/livekit@v1.13.9
    module_dir="$(go env GOPATH)/pkg/mod/github.com/livekit/livekit@v1.13.9"
    cp -a "$module_dir" /tmp/livekit-src
    chmod -R u+w /tmp/livekit-src
    cd /tmp/livekit-src

    go mod edit -require=golang.org/x/net@v0.60.0
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
      go build -mod=mod -trimpath -buildvcs=false -a \
        -o /out/livekit-server ./cmd/server

    livekit_version="$(/out/livekit-server --version)"
    printf "Binary version: %s\n" "$livekit_version"
    test "$livekit_version" = "livekit-server version 1.13.9"
    go version -m /out/livekit-server > /out/build-info.txt
    grep -Fq go1.27.3 /out/build-info.txt || { cat /out/build-info.txt; exit 1; }
    tab="$(printf "\\t")"
    grep -Fq "golang.org/x/net${tab}v0.60.0" /out/build-info.txt || { cat /out/build-info.txt; exit 1; }
    grep -Fq "google.golang.org/grpc${tab}v1.84.0" /out/build-info.txt || { cat /out/build-info.txt; exit 1; }
    printf "Compiler and module versions verified.\n"

    cp LICENSE /out/LICENSE
    tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
      --directory=/out --create --file=- LICENSE livekit-server \
      | gzip --no-name > /out/livekit.tar.gz
    printf "Created the standalone archive.\n"
  '

install -m 0755 "$BUILD_DIR/livekit-server" "$SCRIPT_DIR/livekit-server"
install -m 0644 "$BUILD_DIR/livekit.tar.gz" "$SCRIPT_DIR/livekit.tar.gz"

printf 'Built LiveKit %s with Go %s and golang.org/x/net %s\n' \
  1.13.9 1.27.3 0.60.0
