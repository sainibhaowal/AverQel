# AverQel Electron Desktop

The AverQel desktop client is packaged with Electron and uses the shared Next.js
frontend. The packaged application opens the production AverQel web origin so
OAuth cookies, session refresh, and the web experience remain consistent.

## Development

Start the frontend development server and Electron together with one command:

```bash
pnpm electron dev
```

By default Electron opens the local frontend at `http://127.0.0.1:1030`. To use
the local API at `http://127.0.0.1:1000` and never contacts the VPS. To use the
local HTTPS reverse proxy instead, set both values explicitly:

```bash
ELECTRON_START_URL=https://averqel.localhost \
NEXT_PUBLIC_API_URL=https://averqel.localhost/api/v1 \
pnpm electron dev
```

## Packaging

```bash
BUILD_TARGET=desktop pnpm --dir frontend build
pnpm --dir applications/desktop build:linux
```

The release workflow builds Linux `.deb`/`.rpm`, Windows `.exe`, and macOS
`.dmg` packages.
