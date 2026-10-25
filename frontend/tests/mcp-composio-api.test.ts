import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchWithAuth = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({ fetchWithAuth }));

import { getComposioStatus, getComposioToolkit, getComposioToolkits } from "../lib/mcp-api";

describe("Composio catalog API requests", () => {
  beforeEach(() => {
    fetchWithAuth.mockReset();
    fetchWithAuth.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ configured: true }),
    });
  });

  it("bounds setup and catalog requests and forwards cancellation", async () => {
    const controller = new AbortController();

    await getComposioStatus({ signal: controller.signal });
    await getComposioToolkits(
      { q: "calendar", cursor: "page-2", limit: 24 },
      { signal: controller.signal },
    );

    expect(fetchWithAuth).toHaveBeenNthCalledWith(1, "/mcp/composio/status", {
      signal: controller.signal,
      timeoutMs: 20_000,
      silentTimeout: true,
      headers: {},
    });
    expect(fetchWithAuth).toHaveBeenNthCalledWith(
      2,
      "/mcp/composio/toolkits?q=calendar&cursor=page-2&limit=24",
      {
        signal: controller.signal,
        timeoutMs: 20_000,
        silentTimeout: true,
        headers: {},
      },
    );
  });

  it("preserves leading underscores in toolkit detail routes", async () => {
    await getComposioToolkit("_1password");

    expect(fetchWithAuth).toHaveBeenCalledWith("/mcp/composio/toolkits/_1password", {
      timeoutMs: 20_000,
      silentTimeout: true,
      headers: {},
    });
  });
});
