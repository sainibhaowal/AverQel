# Release security and artifact boundaries

The desktop release and VPS deployment are separate manual workflows. Run the
desktop workflow only from protected `main`; it publishes desktop installers to
GitHub Releases and never starts a VPS deployment.

## Desktop release contents

| Item | Release behavior |
| --- | --- |
| Linux | Builds `AverQel-linux-amd64.deb` |
| Windows | Builds `AverQel-windows-x64.exe` |
| Electron | Packages the AverQel desktop shell and shared AverQel frontend |
| Size | Blocks publication if either compressed installer exceeds 160 MiB |
| Integrity | Publishes `SHA256SUMS.txt` and `release-manifest.json` with the installers |
| Website downloads | The website points directly to stable GitHub `releases/latest/download` asset URLs |
| Website version label | Comes from the deployed frontend build and updates only when the VPS deployment workflow is run |
| macOS and RPM | Not built or published by this workflow |
| VPS | Not built, changed, or deployed by this workflow |

## Signing status

The current desktop release workflow does not sign installers. The Windows
installer may therefore display the operating system's unknown-publisher
warning. Do not describe the package as signed or notarized. Signing requires a
separate reviewed workflow change and appropriately scoped signing credentials.

## VPS deployment boundary

The manual VPS workflow builds and verifies server images, then deploys them to
the configured VPS. It is independent from the desktop release workflow. A
successful desktop release does not prove that the production website or
backend was deployed or updated.
