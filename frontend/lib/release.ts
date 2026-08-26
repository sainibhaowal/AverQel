const SEMVER_TAG = /^v\d+\.\d+\.\d+$/;

// Keep these references explicit. Next.js inlines NEXT_PUBLIC_* values into
// browser bundles, but cannot inline a value accessed through process.env[name].
const configuredVersion = process.env.NEXT_PUBLIC_APP_VERSION?.trim() || "";

/** The release tag embedded into this web or desktop build. */
export const APP_VERSION = SEMVER_TAG.test(configuredVersion) ? configuredVersion : "development";

/** Public binary directory served by AverQel, with a local fallback. */
export const DESKTOP_DOWNLOAD_BASE_URL =
  process.env.NEXT_PUBLIC_DESKTOP_DOWNLOAD_BASE_URL?.trim() ||
  "https://github.com/sainibhaowal/AverQel/releases/latest/download";

export const DESKTOP_LINUX_DOWNLOAD_URL = `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-linux-amd64.deb`;

export const DESKTOP_WINDOWS_DOWNLOAD_URL = `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-windows-x64.exe`;

export const DESKTOP_MACOS_DOWNLOAD_URL = `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-macos-universal.dmg`;

export const DESKTOP_LINUX_RPM_DOWNLOAD_URL = `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-linux-x86_64.rpm`;
