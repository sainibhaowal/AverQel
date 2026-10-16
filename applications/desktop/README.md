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

### AverQel product mark

The shared product mark is `frontend/public/brand/AverQel_Icon.svg`. The
frontend uses it on the landing, authentication, onboarding, dashboard, and
Electron title-bar surfaces. The packaged shell uses matching derivatives in
`applications/desktop/assets/icon.png`, `icon.ico`, and `icon.icns`; these are
the icons embedded in Linux, Windows, and macOS builds respectively.

The visible text wordmark is `frontend/public/brand/AverQel_Text.svg`, rendered
through `frontend/app/components/ui/AverQelWordmark.tsx` on the web surfaces
loaded inside the shell. The login page uses the complete
`frontend/public/brand/AverQel_Exact_Logo.svg` artwork and its
`INTELLIGENCE ALL YOU NEED` tagline. The Electron preload title bar also loads
the same `/brand/AverQel_Icon.svg` and `/brand/AverQel_Text.svg` URLs, so the
installed window chrome uses both canonical files. The original opaque-canvas
input is retained beside it as `AverQel_Text_Source.svg`.
The web titlebar and Electron preload titlebar use the same compact spacing and
wordmark baseline so the installed shell matches the web lockup.

`pnpm run prepare:brand-assets` stages both canonical SVGs into the Electron
resource tree before any desktop build. The Linux AppStream and desktop-entry
display name is `AverQel`; the Windows NSIS and macOS DMG product names use the
same value from `package.json`.

When updating the mark, regenerate all three desktop formats from the same SVG
and run `pnpm --dir applications/desktop test` before creating a package.

The Linux installer keeps the package ID `averqel-desktop` for upgrade
compatibility. Its software-center listing uses the AppStream name
`AverQel` and a plain-text description; the installed application
menu uses the same display name. The release workflow checks the actual `.deb`
for both the AppStream metadata and an ASCII-only Debian description before it
publishes an installer.

The Linux and Windows build commands verify the generated desktop resource
tree against NeoSIS's runtime manifest before they succeed. The check confirms
the runtime entry point, the AverQel profile, every listed file's size and
SHA-256 checksum, and the target platform and architecture. The Linux release
workflow also extracts the final `.deb` and repeats this verification on the
installer contents before upload. A missing or changed runtime therefore fails
the release job instead of producing a successful release with NeoSIS absent.

The Electron main process owns the OpenAI Codex runtime used by the OpenAI
provider's desktop-only Codex Login tab. It checks for a signed-in ChatGPT
account in the local Codex CLI and, when found, uses the CLI's app-server over
stdio for account/model discovery and inference. AverQel does not read the CLI
credential file or copy its tokens. If no usable ChatGPT CLI login is available,
the user can sign in through OpenAI in the system browser; those OAuth tokens are
encrypted with Electron `safeStorage` in the current operating-system profile.
API-key CLI sessions are not treated as ChatGPT plan access. Provider settings
store an opaque local-account identifier and discovered model metadata; raw
account email and CLI credentials stay on the desktop. The backend relays
inference over a one-use WebSocket ticket and transient request/response frames.
Each Codex model's advertised reasoning efforts, including `minimal`, `ultra`,
and other safe catalog values, stay attached to that model and are sent using
their native Codex values. Browser OAuth uses per-model effort metadata only if
the account's model catalog returns it; otherwise DeepSpace uses its existing
OpenAI model profile.
Codex subprocesses start outside the project in the OS temporary directory, and
each inference uses a private temporary workspace. Inference requires an
app-server permission profile that denies filesystem access except minimal
runtime paths; shell, MCP, hooks, apps, plugins, subagents, web search, and local
Codex history are disabled. CLI versions that cannot enforce this profile are
not used for inference. API keys and other token-like environment variables
are removed from the Codex child-process environment. DeepSpace function tools
are normalized into one AverQel namespace with unique function names before
the CLI turn starts, matching the app-server contract even when the backend
request uses the OpenAI-compatible function form.
Linux OAuth sign-in requires an encrypted GNOME Keyring or KWallet backend;
Electron's `basic_text` fallback is rejected. The Codex app-server RPC surface
can change between CLI releases, so older or incompatible versions fall back to
browser sign-in. The macOS `.dmg` is built with
`pnpm --dir applications/desktop build:mac`. OpenAI's current Sign in with
ChatGPT guidance requires paid or remotely hosted apps to complete its
eligibility process.

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

## LM Studio and Ollama on the user's computer

The desktop build can route a configured LM Studio or Ollama provider to the
same computer that runs AverQel Desktop. Start LM Studio's OpenAI-compatible
server (normally `http://127.0.0.1:1234/v1`) or start Ollama (normally
`http://127.0.0.1:11434`), then choose **This computer** in the provider form.
The Electron main process makes the loopback request and streams normalized
events through the existing authenticated AverQel runtime WebSocket. No model
binary is bundled and no local API key is stored by AverQel. Ollama model pulls
are supported from the provider page; LM Studio model downloads remain managed
by LM Studio.

The desktop local target requires the signed-in desktop app to remain open;
hosted orchestration, authentication, history, and DeepSpace tools still run
through the AverQel backend, so this option does not make the whole product
offline. Remote or server-hosted endpoints remain available through their
hosted provider families; LM Studio and Ollama are intentionally local desktop
connections.

## NeoSIS Local workspace

The desktop build contains one Electron shell. In a packaged desktop build with
the NeoSIS runtime present, signed-in AverQel users can switch to NeoSIS from the
center of the dashboard header or the sidebar item directly below DeepSpace.
Browser users, signed-out users, and the Electron development build do not see
these controls. The desktop window has a controls-only top strip; NeoSIS shows
its AverQel return control in the page below that strip. Returning restores the
last AverQel page in the same window. NeoSIS starts as a private loopback service
with an authenticated launch URL; it does not receive AverQel cookies, API
tokens, tenant data, or server credentials. The local profile opts
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
