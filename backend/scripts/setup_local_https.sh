#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd -- "$BACKEND_DIR/.." && pwd)"

DOMAIN="${AVERQEL_LOCAL_DOMAIN:-averqel.localhost}"
CERTS_DIR="${AVERQEL_TLS_CERTS_DIR:-$BACKEND_DIR/.local/certs}"
CERT_FILE="$CERTS_DIR/averqel.localhost.pem"
KEY_FILE="$CERTS_DIR/averqel.localhost-key.pem"

if ! command -v mkcert >/dev/null 2>&1; then
  echo "mkcert is required to generate trusted local HTTPS certificates." >&2
  echo "Install it first, for example:" >&2
  echo "  sudo apt install libnss3-tools" >&2
  echo "  brew install mkcert nss   # on macOS/Linuxbrew" >&2
  echo "Then rerun this script." >&2
  exit 1
fi

mkdir -p "$CERTS_DIR"

mkcert -install
mkcert \
  -cert-file "$CERT_FILE" \
  -key-file "$KEY_FILE" \
  "$DOMAIN" \
  localhost \
  127.0.0.1 \
  ::1

cat <<EOF
Generated local HTTPS certificate assets:
  cert: $CERT_FILE
  key:  $KEY_FILE

Use local production with:
  AVERQEL_DOMAIN=$DOMAIN
  AVERQEL_PUBLIC_ORIGIN=https://$DOMAIN

Open:
  https://$DOMAIN
EOF
