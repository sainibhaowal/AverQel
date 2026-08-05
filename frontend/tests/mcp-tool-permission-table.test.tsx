import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPToolPermissionTable from "../app/dashboard/mcp/_components/MCPToolPermissionTable";
import { tools } from "./mcp-test-fixtures";

const { updateMCPToolPolicy } = vi.hoisted(() => ({ updateMCPToolPolicy: vi.fn() }));
vi.mock("@/lib/mcp-api", () => ({ updateMCPToolPolicy }));

describe("MCPToolPermissionTable", () => {
  it("offers the three explicit permission modes and persists a block", async () => {
    updateMCPToolPolicy.mockResolvedValue({ ...tools[0], mode: "blocked" });
    render(<MCPToolPermissionTable serverId="server-1" tools={tools} />);
    const selector = screen.getByRole("combobox", { name: "Permission for search_mail" });
    expect(screen.getAllByRole("option", { name: "always allow" })).not.toHaveLength(0);
    expect(screen.getAllByRole("option", { name: "needs approval" })).not.toHaveLength(0);
    expect(screen.getAllByRole("option", { name: "blocked" })).not.toHaveLength(0);
    fireEvent.change(selector, { target: { value: "blocked" } });
    await waitFor(() =>
      expect(updateMCPToolPolicy).toHaveBeenCalledWith("server-1", "search_mail", "blocked"),
    );
  });
});
