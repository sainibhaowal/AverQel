import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const callbackMocks = vi.hoisted(() => ({
  completeComposioOAuth: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("@/lib/mcp-api", () => callbackMocks);
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: callbackMocks.replace }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

import ComposioCallbackClient from "../app/dashboard/mcp/composio/callback/ComposioCallbackClient";

describe("Composio OAuth callback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(
      {},
      "",
      "/dashboard/mcp/composio/callback?toolkit_slug=gmail&connected_account_id=ca_123&status=success",
    );
    callbackMocks.completeComposioOAuth.mockResolvedValue({
      status: "connecting",
      server_id: "server-123",
    });
  });

  it("sends the returned app and account to AverQel for owner verification", async () => {
    render(<ComposioCallbackClient />);

    await waitFor(() =>
      expect(callbackMocks.completeComposioOAuth).toHaveBeenCalledWith({
        toolkitSlug: "gmail",
        connectedAccountId: "ca_123",
        status: "success",
      }),
    );
    expect(window.location.search).toBe("");
    await waitFor(() =>
      expect(callbackMocks.replace).toHaveBeenCalledWith(
        "/dashboard/mcp?mcp_status=connected&server_id=server-123",
      ),
    );
  });

  it("reports canceled authorization without claiming a connected app", async () => {
    callbackMocks.completeComposioOAuth.mockResolvedValue({
      status: "failed",
      server_id: "server-123",
    });
    render(<ComposioCallbackClient />);

    expect(
      await screen.findByText(/authorization was canceled or did not complete/i),
    ).toBeInTheDocument();
    expect(callbackMocks.replace).not.toHaveBeenCalled();
  });
});
