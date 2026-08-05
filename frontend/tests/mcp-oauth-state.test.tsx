import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPProviderPage from "../app/dashboard/mcp/providers/[entryId]/page";
const { startMCPServerOAuth } = vi.hoisted(() => ({ startMCPServerOAuth: vi.fn() }));
vi.mock("next/navigation", () => ({ useParams: () => ({ entryId: "provider-1" }) }));
vi.mock("@/lib/mcp-api", () => ({
  getMarketplaceEntry: vi.fn().mockResolvedValue({
    id: "provider-1",
    name: "Community Mail",
    publisher: "Publisher",
    description: "Mail",
    transport: "streamable_http",
    remote_url: "https://provider.example/mcp",
    categories: [],
    official: false,
    verified: true,
    source: "curated",
    action: "connect",
    tool_count: 1,
    capabilities: [],
    tool_preview: [],
    tools: [],
    catalog_status: "ready",
    auth_type: "oauth",
    trust_status: "approved",
    publisher_type: "community",
    badges: { community: true },
    trusted_logo_key: "unknown-provider",
    supported_products: [],
    tool_categories: [],
    risk_policy: {},
    health: { status: "healthy", last_checked_at: null },
    requested_scopes: ["mail.read"],
    connectable: true,
  }),
  listMCPServers: vi.fn().mockResolvedValue([]),
  connectMarketplaceEntry: vi.fn(),
  startMCPServerOAuth,
  safeExternalUrl: (value: string | null | undefined) => value || null,
}));

describe("MCP OAuth state flow", () => {
  it("starts OAuth through the API boundary without exposing credentials", async () => {
    startMCPServerOAuth.mockResolvedValue({
      authorization_url: "https://provider.example/oauth",
      status: "started",
    });
    render(<MCPProviderPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument(),
    );
    expect(screen.queryByText(/client_secret|access_token|refresh_token/i)).not.toBeInTheDocument();
  });
});
