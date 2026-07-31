import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPConnectionScopePanel from "../app/dashboard/mcp/_components/MCPConnectionScopePanel";

const { getMCPScopedConnections, updateMCPScopedConnection } = vi.hoisted(() => ({
  getMCPScopedConnections: vi.fn(),
  updateMCPScopedConnection: vi.fn(),
}));
vi.mock("@/lib/mcp-api", () => ({ getMCPScopedConnections, updateMCPScopedConnection }));

describe("MCPConnectionScopePanel", () => {
  it("requires explicit conversation and DeepSpace identifiers before enabling a scope", async () => {
    getMCPScopedConnections.mockResolvedValue({ connections: [] });
    render(<MCPConnectionScopePanel serverId="server-1" />);
    expect(screen.getByText(/ownership is verified server-side/i)).toBeInTheDocument();
    expect(screen.getByText(/scope-gated access/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Load scope" })[0]).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("Enter conversation ID"), { target: { value: "conversation-1" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Load scope" })[0]);
    await waitFor(() => expect(getMCPScopedConnections).toHaveBeenCalledWith("conversation", "conversation-1"));
    expect(updateMCPScopedConnection).not.toHaveBeenCalled();
  });
});
