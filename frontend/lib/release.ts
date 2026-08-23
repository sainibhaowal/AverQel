const GITHUB_RELEASES_URL = "https://github.com/sainibhaowal/AverQel/releases";
const SEMVER_TAG = /^v\d+\.\d+\.\d+$/;

function publicBuildValue(name: "NEXT_PUBLIC_APP_VERSION" | "NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL") {
  return process.env[name]?.trim() || "";
}

const configuredVersion = publicBuildValue("NEXT_PUBLIC_APP_VERSION");

/** The release tag embedded into this web or desktop build. */
export const APP_VERSION = SEMVER_TAG.test(configuredVersion) ? configuredVersion : "development";

/**
 * A release-specific page when built by the VPS workflow, with a stable latest
 * release fallback for local development builds.
 */
export const DESKTOP_DOWNLOAD_URL =
  publicBuildValue("NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL") || `${GITHUB_RELEASES_URL}/latest`;
