# AverQel Brand Guide

This guide identifies the official AverQel visual assets and gives practical
rules for using them.

## Official assets

The repository’s official product assets are:

- `frontend/public/brand/AverQel_Icon.svg` — the shared application icon; and
- `frontend/public/brand/AverQel_Text.svg` — the shared text wordmark; and
- `frontend/public/brand/AverQel_Exact_Logo.svg` — the complete login logo artwork.
- `frontend/public/AverQel Logo/deepspace-telemetry-parabola.svg` — the Qel Connect feature mark.

The landing page, web workspace, documentation shell, Electron title bar, and
desktop installer metadata use the icon and text wordmark. The login page uses
the complete logo artwork and its `INTELLIGENCE ALL YOU NEED` tagline. Electron's
platform-specific PNG, ICO, and ICNS files are generated from the canonical
icon for operating-system packaging. DeepSpace navigation uses its dedicated
RGB orbital logo at
`frontend/public/DeepSpace Logo/DeepSpace_OrangeGreenBlue_LogoOnly_Final.svg`
next to the visible “DeepSpace” label. The repository banner is maintained
separately under `Docs/brand/`.

Qel Connect is the user-facing name for the shared project-space product
formerly exposed as Collections. Use the telemetry parabola mark beside that
label in product surfaces. Keep `/collections` routes, API fields, permission
codes, and storage identifiers unchanged for compatibility.

DeepSpace loading and welcome indicators use
`frontend/public/AverQel Logo/deepspace-wormhole-aperture.svg`; only its outer
capsule aperture rotates clockwise while the internal star remains fixed.

The login artwork remains unchanged as the accessible base image. A decorative
CSS layer may add a right-to-left RGB sweep over only the `AVER` and `EL`
letter regions; the `Q` stays in its original colors and the source SVG is not
modified.

The official product name is `AverQel`. Keep the capitalization exactly as
shown.

## Use the official assets only for the official project

The official logo and icon may be used in the AverQel repository, official
documentation, official website, and official releases. When referring to the
upstream project, use the assets without altering their proportions or adding
elements that could imply a different source.

Do not:

- use the AverQel logo or icon for a fork, replacement, competing service, or
  modified desktop application;
- alter, redraw, recolor, distort, or combine the logo with another product’s
  branding in a way that suggests official status;
- use the AverQel name or logo in a domain, company name, package name, or app
  name that implies an official relationship; or
- use `®` for AverQel unless and until the relevant mark is formally registered.

Forks and modified distributions should replace the wordmark, icon, desktop
application name, package identifier, and other official identity elements.
They may include a truthful “based on AverQel” acknowledgement with a link to
the upstream project.

## Attribution

When displaying the AverQel name or logo in a factual reference, use a clear
statement such as:

> AverQel is an open-source project licensed under Apache-2.0. AverQel and
> the AverQel logos are project brand identifiers and are not granted for
> unrelated branding use.

Because the marks are not claimed here as registered, `AverQel™` may be used
where appropriate; do not use `AverQel®` before registration.
