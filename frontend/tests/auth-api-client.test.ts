import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchWithAuth, resetAuthSessionState } from "../lib/api";

const fetchMock = vi.fn();

function base64UrlEncode(value: unknown): string {
  return btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function createJwt(expOffsetSeconds: number): string {
  const header = base64UrlEncode({ alg: "none", typ: "JWT" });
  const payload = base64UrlEncode({
    exp: Math.floor((Date.now() + expOffsetSeconds * 1000) / 1000),
  });
  return `${header}.${payload}.signature`;
}

describe("fetchWithAuth", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    resetAuthSessionState();
    localStorage.clear();
    localStorage.setItem("averqel_token", createJwt(30));
    localStorage.setItem("averqel_tenant_id", "tenant-1");

    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/auth/refresh")) {
        return new Response(JSON.stringify({ detail: "Refresh token expired" }), {
          status: 401,
          headers: {
            "Content-Type": "application/json",
          },
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    resetAuthSessionState();
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("does not send the protected request after a failed proactive refresh", async () => {
    const response = await fetchWithAuth("/dashboard/overview");

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/auth/refresh");
    expect(localStorage.getItem("averqel_token")).toBeNull();

    const followUp = await fetchWithAuth("/collections/notifications");

    expect(followUp.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
