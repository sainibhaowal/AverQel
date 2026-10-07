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

  it("keeps long provider documentation collapsed until requested", async () => {
    const longDescription =
      "Search the connected workspace. " + "Additional provider schema details. ".repeat(80);
    render(
      <MCPToolPermissionTable
        serverId="server-1"
        tools={[{ ...tools[0], description: longDescription }]}
      />,
    );

    expect(screen.getByText("Search the connected workspace.")).toBeInTheDocument();
    expect(screen.queryByText(/Additional provider schema details/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show full details for search_mail" }));
    await waitFor(() =>
      expect(screen.getByText(/Additional provider schema details/)).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Hide full details for search_mail" }),
    ).toHaveAttribute("aria-expanded", "true");
  });
});
