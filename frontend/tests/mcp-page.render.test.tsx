import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import MCPDashboard from "../app/dashboard/mcp/page";

const fetchWithAuthMock = vi.fn();
const searchParamsMock = { value: new URLSearchParams() };
const routerMock = { replace: vi.fn() };

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParamsMock.value,
  useRouter: () => routerMock,
}));

vi.mock("lucide-react", async () => {
  const actual = await vi.importActual<typeof import("lucide-react")>("lucide-react");
  return actual;
});

function jsonResponse(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

function installApiFixtures({ configured = true } = {}) {
  fetchWithAuthMock.mockImplementation(async (path: string) => {
    if (path === "/mcp/servers") {
      return jsonResponse([
        {
          id: "installed-1",
          name: "Installed Composio App",
          status: "connected",
          transport: "streamable_http",
          provider_slug: "composio:google_calendar",
          config: {
            oauth_mode: "mcp_oauth",
            mcp_catalog_tool_count: 2,
            mcp_catalog_last_sync_at: "2026-07-18T09:58:00Z",
          },
          account_identity: { email: "owner@example.com" },
          last_error: null,
        },
      ]);
    }
    if (path === "/mcp/composio/status") {
      return jsonResponse({
        configured,
        oauth_callback_ready: true,
      });
    }
    if (path.startsWith("/mcp/composio/toolkits?")) {
      return jsonResponse({
        items: [
          {
            slug: "google_calendar",
            name: "Google Calendar",
            description: "Manage your calendar",
            categories: ["Productivity"],
            tool_count: 2,
            auth_schemes: ["oauth2"],
            no_auth: false,
          },
        ],
        next_cursor: null,
        current_page: 1,
        total_items: 271,
      });
    }
    return { ok: false, status: 404, json: async () => ({ detail: "Not found" }) };
  });
}

describe("MCP dashboard", () => {
  beforeEach(() => {
    searchParamsMock.value = new URLSearchParams();
    routerMock.replace.mockReset();
    fetchWithAuthMock.mockReset();
    installApiFixtures();
  });

  it("shows Composio as Marketplace and keeps installed connections", async () => {
    render(<MCPDashboard />);

    expect(
      await screen.findByRole("heading", { name: "Connect apps to DeepSpace" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Google Calendar" })).toBeInTheDocument();
    expect(screen.getByText("271 Composio apps available")).toBeInTheDocument();
    expect(screen.queryByText("Google Gmail")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Composio Apps" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /installed \(1\)/i }));
    expect(await screen.findByText("Installed Composio App")).toBeInTheDocument();
    expect(screen.getByText(/Remote HTTP · OAuth · 2 tools/i)).toBeInTheDocument();
  });

  it("opens the same Composio Marketplace for the old Composio tab link and points to Providers when no key exists", async () => {
    searchParamsMock.value = new URLSearchParams("tab=composio");
    installApiFixtures({ configured: false });

    render(<MCPDashboard />);

    expect(
      await screen.findByRole("heading", { name: "Add your Composio key to browse apps" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Providers → MCP" })).toHaveAttribute(
      "href",
      "/dashboard/settings/providers?tab=mcp",
    );
  });

  it("handles a successful OAuth return and opens the connected server", async () => {
    searchParamsMock.value = new URLSearchParams("mcp_status=connected&server_id=server-1");
    render(<MCPDashboard />);
    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith(
        "/dashboard/mcp/inspector/server-1?mcp_status=connected",
      ),
    );
  });

});
