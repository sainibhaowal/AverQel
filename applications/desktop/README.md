# AverQel Electron Desktop

The AverQel desktop client is packaged with Electron and uses the shared Next.js
frontend. The packaged application opens the production AverQel login route so
OAuth cookies, session refresh, and the web experience remain consistent.
Google and GitHub sign-in open in a compact child window that shares the
desktop session. The main AverQel window stays on the login page and returns to
the signed-in workspace after authentication; closing the sign-in window
returns to login with a cancellation message.

Closing the desktop window exits AverQel. Minimizing keeps it in the taskbar,
and launching AverQel again while it is already running focuses the existing
window. AverQel does not run in the system notification area.

## Development

Start the frontend development server and Electron together with one command:

```bash
pnpm electron dev
```

Run the desktop's database-free source-resolution tests with:

```bash
pnpm --dir applications/desktop test
```

By default Electron opens the local frontend login route at
`http://127.0.0.1:1030/auth/login` and uses the local development API
configuration. It does not contact the VPS.
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

The release workflow builds AverQel Linux `.deb` and Windows `.exe` packages
from the AverQel source and shared frontend.

### AverQel product mark

The shared web product mark is `frontend/public/AverQel Logo/AverQel_Icon.svg`.
The frontend uses it on the landing, authentication, onboarding, dashboard,
and other web surfaces. Desktop package icons use the same icon-only source in
`applications/desktop/assets/icon.png`, `icon.ico`, and `icon.icns`. Linux and
the Electron window use the PNG, Windows and its NSIS installer use the ICO,
and macOS uses the ICNS.

The visible text wordmark is `frontend/public/brand/AverQel_Text.svg`, rendered
through `frontend/app/components/ui/AverQelWordmark.tsx` on the web surfaces
loaded inside the shell. The login page uses the complete
`frontend/public/brand/AverQel_Exact_Logo.svg` artwork and its
`INTELLIGENCE ALL YOU NEED` tagline. The Electron preload renders a 40px title
bar with only window controls and no product logo or wordmark. Page scrolling
starts below it. The original opaque-canvas input is retained beside the
wordmark as `AverQel_Text_Source.svg`.

The `prepare:brand-assets` script stages both canonical SVGs into the Electron
resource tree before desktop builds and test runs. The Linux AppStream and
desktop-entry display name is `AverQel`; the Windows NSIS and macOS DMG product
names use the same value from `package.json`.

The desktop PNG is a transparent 512 by 512 square with the centered mark
filling about 80 to 85 percent of the canvas. The ICO and ICNS contain matching
size variants. The source SVG has a wide viewBox with transparent margins, so
trim its transparent edges before fitting it into the square. When updating the
source, regenerate all three desktop formats and run
`pnpm --dir applications/desktop test` before creating a package.

The Linux installer keeps the package ID `averqel-desktop` for upgrade
compatibility. Its software-center listing uses the AppStream name
`AverQel` and a plain-text description; the installed application
menu uses the same display name. The release workflow checks the actual `.deb`
for both the AppStream metadata and an ASCII-only Debian description before it
publishes an installer.

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
