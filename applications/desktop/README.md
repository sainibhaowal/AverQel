# AverQel Electron Desktop

The AverQel desktop client is packaged with Electron and uses the shared Next.js
frontend. The packaged application opens the production AverQel web origin so
OAuth cookies, session refresh, and the web experience remain consistent.

## Development

Start the frontend development server and Electron together with one command:

```bash
pnpm electron dev
```

Run the desktop's database-free source-resolution tests with:

```bash
pnpm --dir applications/desktop test
```

By default Electron opens the local frontend at `http://127.0.0.1:1030` and
uses the local development API configuration. It does not contact the VPS.
To use the local HTTPS reverse proxy instead, set both values explicitly:

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

The release workflow builds Linux `.deb` and Windows `.exe` packages. Both
include the NeoSIS desktop runtime from the NeoSIS repository's pinned `main`
commit recorded in the GitHub release manifest.

Linux packaging builds NeoSIS's static Landlock launcher with `musl-gcc`. The
release workflow installs Ubuntu's `musl-tools` package on the Linux runner;
local Ubuntu builds need the same package:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends --yes musl-tools
```

Each release runner creates the matching ignored NeoSIS `.env` file from the
pinned checkout's template for `--prepare-only` runtime staging. It includes
only the application ID and test policy settings required by that validation;
the reserved `test.example.com` origin is not used for network requests or
copied into the AverQel package. Signing credentials are not included.

The desktop pnpm policy allows the `electron-winstaller` install script only.
That reviewed script copies its bundled 7-Zip binaries to the names required by
Windows installer packaging; keep this allowlist narrow rather than enabling
dependency build scripts globally.

## NeoSIS Local workspace

The desktop build contains one Electron shell. Signed-in AverQel users can open
the NeoSIS Local workspace from the desktop title bar. NeoSIS starts as a private
loopback service with an authenticated launch URL; it does not receive AverQel
cookies, API tokens, tenant data, or server credentials. The local profile opts
the sidebar Browser into NeoSIS, since the standard Web profile keeps it off by
default. NeoSIS receives only the operating-system runtime variables it needs
and its own `NEOSIS_HOME`; AverQel credentials and server configuration are not
forwarded to the child process. Open NeoSIS's right sidebar to use Browser.

For Linux builds, `pnpm --dir applications/desktop build:linux` prepares the
production NeoSIS runtime from `neosis/` in the AverQel workspace, or from the
adjacent `AverQel Neosis/` checkout when present. Set `NEOSIS_SOURCE_DIR` to use
another local clone path. The separate NeoSIS Electron application is not
included. The packaged NeoSIS runtime uses the same Electron executable as
AverQel. The development launcher uses the same source lookup order, so the
adjacent `AverQel Neosis/` checkout works without moving or copying its source
into this repository.
