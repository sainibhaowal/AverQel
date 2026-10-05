const DEVICE_ID_STORAGE_KEY = "averqel.auth.session-device.v1";

export type AuthSessionDevice = {
  device_id?: string;
  device_label: string;
};

function createOpaqueDeviceId(): string | null {
  if (typeof crypto === "undefined" || !crypto.getRandomValues) return null;
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `browser-${hex}`;
}

function browserLabel(userAgent: string): string {
  const browser = /Edg\//.test(userAgent)
    ? "Edge"
    : /Firefox\//.test(userAgent)
      ? "Firefox"
      : /(?:Chrome|Chromium)\//.test(userAgent)
        ? "Chrome"
        : /Safari\//.test(userAgent)
          ? "Safari"
          : "Browser";
  const platform = /iPhone|iPad|iPod/i.test(userAgent)
    ? "iOS"
    : /Android/i.test(userAgent)
      ? "Android"
      : /Windows/i.test(userAgent)
        ? "Windows"
        : /Mac OS|Macintosh/i.test(userAgent)
          ? "macOS"
          : /Linux/i.test(userAgent)
            ? "Linux"
            : "";
  return platform ? `${browser} on ${platform}` : browser;
}

/** Return a random per-browser identifier; this does not fingerprint hardware. */
export function getAuthSessionDevice(): AuthSessionDevice {
  const userAgent = typeof navigator === "undefined" ? "" : navigator.userAgent;
  let deviceId: string | null = null;
  try {
    deviceId = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY);
  } catch {
    // Private browsing or storage policy can disable localStorage.
  }

  if (!deviceId || !/^browser-[a-f0-9]{32}$/.test(deviceId)) {
    deviceId = createOpaqueDeviceId();
    if (deviceId) {
      try {
        window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, deviceId);
      } catch {
        // A generated in-memory ID still makes this sign-in distinguishable.
      }
    }
  }

  return {
    device_label: browserLabel(userAgent),
    ...(deviceId ? { device_id: deviceId } : {}),
  };
}
