import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPProviderPage from "../app/dashboard/mcp/providers/[entryId]/page";
vi.mock("@/lib/mcp-api", () => ({
  getMarketplaceEntry: vi.fn().mockResolvedValue({ id: "provider-1", name: "Community Mail", publisher: "Publisher", description: "Mail", transport: "streamable_http", remote_url: "https://provider.example/mcp", categories: [], official: false, verified: true, source: "curated", action: "connect", tool_count: 1, capabilities: [], tool_preview: [], tools: [], catalog_status: "ready", auth_type: "oauth", trust_status: "approved", publisher_type: "community", badges: { community: true }, trusted_logo_key: "unknown-provider", supported_products: [], tool_categories: [], risk_policy: {}, health: { status: "healthy", last_checked_at: null }, requested_scopes: ["mail.read"], connectable: true }),
  listMCPServers: vi.fn().mockResolvedValue([]),
  connectMarketplaceEntry: vi.fn(),
  startMCPServerOAuth: vi.fn(),
  safeExternalUrl: (value: string | null | undefined) => value || null,
}));

describe("MCP provider detail page", () => {
  it("loads provider details from the API and exposes a connect action", async () => {
    render(<MCPProviderPage params={{ entryId: "provider-1" }} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Community Mail" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument();
    expect(screen.getByText("mail.read")).toBeInTheDocument();
  });
});
