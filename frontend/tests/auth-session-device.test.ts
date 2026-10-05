import { beforeEach, describe, expect, it } from "vitest";

import { getAuthSessionDevice } from "../lib/auth-session-device";

describe("auth session device metadata", () => {
  beforeEach(() => localStorage.clear());

  it("reuses a random browser ID without exposing the user-agent as the label", () => {
    Object.defineProperty(window.navigator, "userAgent", {
      configurable: true,
      value: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153.0.0.0 Safari/537.36",
    });

    const first = getAuthSessionDevice();
    const second = getAuthSessionDevice();

    expect(first.device_id).toMatch(/^browser-[a-f0-9]{32}$/);
    expect(second.device_id).toBe(first.device_id);
    expect(first.device_label).toBe("Chrome on Linux");
    expect(first.device_label).not.toContain("Mozilla");
  });
});
