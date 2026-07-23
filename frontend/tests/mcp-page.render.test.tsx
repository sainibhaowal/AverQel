import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import MCPDashboard from "../app/dashboard/mcp/page";

const fetchWithAuthMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("lucide-react", async () => {
  const actual = await vi.importActual<typeof import("lucide-react")>("lucide-react");
  return actual;
});

describe("MCP dashboard", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "registry-1",
              name: "Example Remote MCP",
              publisher: "Example Publisher",
              description: "An approved official Google Workspace MCP application.",
              transport: "streamable_http",
              remote_url: "https://mcp.example.com/mcp",
              categories: ["productivity", "files"],
              official: true,
              verified: true,
              source: "official_registry",
              oauth_requirements: { type: "oauth" },
              package_metadata: { discovered_capabilities: ["search_files", "get_file"] },
              action: "connect",
              logo_url: null,
              tool_count: 18,
              last_catalog_sync_at: "2026-07-18T10:00:00Z",
              verification_reason: "registry metadata",
              last_seen_at: "2026-07-18T10:00:00Z",
              capabilities: ["search_files", "get_file"],
              tool_preview: [{ name: "search_files", description: "Search files" }],
              catalog_status: "anonymous_catalog",
              auth_type: "oauth",
              trust_status: "approved",
            },
            {
              id: "registry-2",
              name: "Example Setup MCP",
              publisher: "Example Publisher",
              description: "A registry MCP server requiring setup.",
              transport: "streamable_http",
              remote_url: "https://setup.example.com/mcp",
              categories: ["communication"],
              official: true,
              verified: false,
              source: "official_registry",
              oauth_requirements: { type: "vendor_registration_required" },
              package_metadata: { discovered_capabilities: ["list_channels"] },
              action: "connect",
              logo_url: null,
              tool_count: 12,
              last_catalog_sync_at: "2026-07-18T10:00:00Z",
              verification_reason: "registry metadata only",
              last_seen_at: "2026-07-18T10:00:00Z",
              capabilities: ["list_channels"],
              docs_url: "https://example.com/docs/mcp",
              trust_status: "discovered",
              connectable: false,
              connectability_reason: "OAuth provider profile is not configured yet.",
            },
          ],
          total: 1,
          page: 1,
          page_size: 24,
          pages: 1,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            id: "installed-1",
            name: "Installed Remote MCP",
            status: "connected",
            transport: "streamable_http",
            config: {
              oauth_mode: "mcp_oauth",
              mcp_tools_cache: [{ name: "search_files" }, { name: "get_file" }],
              mcp_catalog_last_sync_at: "2026-07-18T09:58:00Z",
            },
            last_error: null,
          },
        ],
      });
  });

  it("renders the marketplace controls, cards, installed status, and details modal", async () => {
    render(<MCPDashboard />);

    expect(await screen.findByText("MCP Marketplace")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /more filters and install options/i }));
    expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Productivity" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verified" })).toBeInTheDocument();
    expect(screen.getByText("Example Remote MCP")).toBeInTheDocument();
    expect(screen.getAllByText("OFFICIAL")).toHaveLength(2);
    expect(screen.getAllByText("VERIFIED")).toHaveLength(1);
    expect(screen.getByText("18 tools")).toBeInTheDocument();
    expect(screen.getByText("search_files")).toBeInTheDocument();
    expect(screen.queryByText("Sync registry")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Setup pending" })).toBeDisabled();
    expect(screen.getByText("OAuth provider profile is not configured yet.")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "View details" })[0]);

    expect(await screen.findByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Last verified")).toBeInTheDocument();
    expect(screen.getByText("Search files")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Connect Example Remote MCP" })).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    fireEvent.click(screen.getByRole("button", { name: /installed \(1\)/i }));

    await waitFor(() => {
      expect(screen.getByText("CONNECTED")).toBeInTheDocument();
      expect(screen.getByText(/Remote · OAuth · 2 tools/i)).toBeInTheDocument();
      expect(screen.getByText(/Last catalog sync:/i)).toBeInTheDocument();
    });
  });
});
