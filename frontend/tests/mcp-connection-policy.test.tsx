import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MCPConnectionPolicyPanel from "../app/dashboard/mcp/_components/MCPConnectionPolicyPanel";
import { policy } from "./mcp-test-fixtures";

const { updateMCPPolicy } = vi.hoisted(() => ({ updateMCPPolicy: vi.fn() }));
vi.mock("@/lib/mcp-api", async () => ({
  ...(await vi.importActual("@/lib/mcp-api")),
  updateMCPPolicy,
}));

describe("MCPConnectionPolicyPanel", () => {
  beforeEach(() => {
    updateMCPPolicy.mockReset().mockResolvedValue(policy);
  });

  it("preserves conservative read-only and approval settings when saved", async () => {
    render(<MCPConnectionPolicyPanel serverId="server-1" policy={policy} />);
    fireEvent.click(screen.getByRole("button", { name: "Save policy" }));
    await waitFor(() =>
      expect(updateMCPPolicy).toHaveBeenCalledWith(
        "server-1",
        expect.objectContaining({
          read_only: true,
          risk_ceiling: "read",
          default_enabled: false,
        }),
      ),
    );
    expect(screen.getByText(/blocked or disabled tool is removed/i)).toBeInTheDocument();
  });
});
