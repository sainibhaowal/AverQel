import { afterEach, describe, expect, it } from "vitest";

import { resolveApiBaseUrl } from "../lib/api";

describe("resolveApiBaseUrl", () => {
  const originalWindow = globalThis.window;
  const setWindow = (value: Window | undefined) => {
    Object.defineProperty(globalThis, "window", {
      value,
      configurable: true,
      writable: true,
    });
  };

  afterEach(() => {
    setWindow(originalWindow);
  });

  it("uses same-origin api path for local docker frontend", () => {
    setWindow({} as Window);
    expect(
      resolveApiBaseUrl({
        hostname: "127.0.0.1",
        protocol: "http:",
        port: "1030",
      }),
    ).toBe("/api/v1");
  });

  it("uses same-origin https api path for production-style local hostnames", () => {
    setWindow(undefined);
    expect(
      resolveApiBaseUrl({
        hostname: "averqel.ravi",
        protocol: "https:",
        port: "443",
      }),
    ).toBe("https://averqel.ravi/api/v1");
  });

  it("keeps local docker clients on same-origin routing even if an env url exists", () => {
    setWindow({} as Window);
    expect(
      resolveApiBaseUrl({
        hostname: "localhost",
        protocol: "http:",
        port: "1030",
        envUrl: "https://api.example.com/api/v1",
      }),
    ).toBe("/api/v1");
  });
});
