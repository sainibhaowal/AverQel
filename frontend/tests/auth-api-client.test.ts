import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const toastMocks = vi.hoisted(() => ({ error: vi.fn() }));

vi.mock("react-hot-toast", () => ({
  default: {
    error: toastMocks.error,
    success: vi.fn(),
  },
}));

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
    toastMocks.error.mockReset();
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
    vi.useRealTimers();
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

  it("does not deadlock when a protected request receives 401", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        return new Response(JSON.stringify({ detail: "Refresh token expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 });
    });

    const response = await fetchWithAuth("/dashboard/overview", { timeoutMs: 100 });

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem("averqel_token")).toBeNull();
  });

  it("rejects a stalled request with a bounded timeout", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    fetchMock.mockImplementation(
      async (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted", "AbortError"));
          });
        }),
    );

    await expect(fetchWithAuth("/dashboard/overview", { timeoutMs: 10 })).rejects.toMatchObject({
      name: "ApiRequestTimeoutError",
      endpoint: "/dashboard/overview",
    });
  });

  it("retries a bounded SERVICE_OVERLOAD response for safe reads", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    vi.useFakeTimers();
    const busyResponse = () =>
      new Response(JSON.stringify({ error: { code: "SERVICE_OVERLOAD", message: "busy" } }), {
        status: 503,
        headers: { "Content-Type": "application/json", "Retry-After": "1" },
      });
    fetchMock
      .mockResolvedValueOnce(busyResponse())
      .mockResolvedValueOnce(busyResponse())
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }));

    const request = fetchWithAuth("/providers");
    await vi.advanceTimersByTimeAsync(2_100);
    const response = await request;

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("never retries a write after SERVICE_OVERLOAD", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: "SERVICE_OVERLOAD", message: "busy" } }), {
        status: 503,
        headers: { "Content-Type": "application/json", "Retry-After": "1" },
      }),
    );

    const response = await fetchWithAuth("/deepspace/chats", {
      method: "POST",
      body: JSON.stringify({ prompt: "must not be replayed" }),
    });

    expect(response.status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not hide a network error from a retried safe read", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { code: "SERVICE_OVERLOAD", message: "busy" } }), {
          status: 503,
          headers: { "Content-Type": "application/json", "Retry-After": "1" },
        }),
      )
      .mockRejectedValueOnce(new TypeError("network unavailable"));

    const request = fetchWithAuth("/providers");
    const rejected = expect(request).rejects.toThrow("network unavailable");
    await vi.advanceTimersByTimeAsync(1_100);

    await rejected;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("lets a page own failed-request messaging without emitting a duplicate global toast", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { message: "Temporary server failure" } }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const response = await fetchWithAuth("/documents/document-1/full-text", {
      suppressErrorToast: true,
    });

    expect(response.status).toBe(500);
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("preserves quiet error handling when authentication refresh retries the request", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    let documentRequestCount = 0;
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        return new Response(JSON.stringify({ access_token: createJwt(300) }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      documentRequestCount += 1;
      if (documentRequestCount === 1) {
        return new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 });
      }
      return new Response(JSON.stringify({ error: { message: "Temporary server failure" } }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    });

    const response = await fetchWithAuth("/documents/document-1/full-text", {
      suppressErrorToast: true,
    });

    expect(response.status).toBe(500);
    expect(documentRequestCount).toBe(2);
    expect(toastMocks.error).not.toHaveBeenCalled();
  });

  it("keeps global request-error toasts enabled by default", async () => {
    localStorage.setItem("averqel_token", createJwt(300));
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { message: "Temporary server failure" } }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await fetchWithAuth("/documents/document-1/full-text");

    expect(toastMocks.error).toHaveBeenCalledWith("Temporary server failure");
  });
});
