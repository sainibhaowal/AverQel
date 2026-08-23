const SEMVER_TAG = /^v\d+\.\d+\.\d+$/;

function publicBuildValue(
  name: "NEXT_PUBLIC_APP_VERSION" | "NEXT_PUBLIC_DESKTOP_DOWNLOAD_BASE_URL",
) {
  return process.env[name]?.trim() || "";
}

const configuredVersion = publicBuildValue("NEXT_PUBLIC_APP_VERSION");

/** The release tag embedded into this web or desktop build. */
export const APP_VERSION = SEMVER_TAG.test(configuredVersion) ? configuredVersion : "development";

/** Public binary directory served by AverQel, with a local fallback. */
export const DESKTOP_DOWNLOAD_BASE_URL =
  publicBuildValue("NEXT_PUBLIC_DESKTOP_DOWNLOAD_BASE_URL") || "/downloads/latest";

export const DESKTOP_LINUX_DOWNLOAD_URL =
  `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-linux-amd64.deb`;

export const DESKTOP_WINDOWS_DOWNLOAD_URL =
  `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-windows-x64.exe`;

export const DESKTOP_MACOS_DOWNLOAD_URL =
  `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-macos-universal.dmg`;

export const DESKTOP_LINUX_RPM_DOWNLOAD_URL =
  `${DESKTOP_DOWNLOAD_BASE_URL.replace(/\/$/, "")}/AverQel-linux-x86_64.rpm`;
