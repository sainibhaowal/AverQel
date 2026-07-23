import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { providerEntry } = vi.hoisted(() => ({ providerEntry: {
  id: "provider-1",
  name: "Route Provider",
  publisher: "Provider",
  description: "Reviewed provider",
  transport: "streamable_http",
  remote_url: "https://provider.example/mcp",
  categories: ["Productivity"],
  official: true,
  verified: true,
  source: "curated",
  action: "connect",
  tool_count: 1,
  capabilities: ["read_data"],
  tool_preview: [{ name: "read_data", description: "Read data", category: "Data", risk_labels: ["read"] }],
  tools: [{ name: "read_data", description: "Read data", category: "Data", risk_labels: ["read"] }],
  catalog_status: "ready",
  auth_type: "oauth",
  trust_status: "approved",
  publisher_type: "official",
  badges: { official: true },
  supported_products: ["Provider"],
  tool_categories: ["Data"],
  risk_policy: {},
  health: { status: "healthy", last_checked_at: null },
  requested_scopes: ["provider.read"],
  connectable: true,
} }));

vi.mock("@/lib/mcp-api", () => ({
  getMarketplaceEntry: vi.fn().mockResolvedValue(providerEntry),
  listMCPServers: vi.fn().mockResolvedValue([]),
  connectMarketplaceEntry: vi.fn(),
  startMCPServerOAuth: vi.fn(),
  safeExternalUrl: (value: string | null | undefined) => value || null,
}));

import MCPProviderPage from "../app/dashboard/mcp/providers/[entryId]/page";

describe("MCP provider detail route", () => {
  it("loads the API-backed provider detail page", async () => {
    render(<MCPProviderPage params={{ entryId: "provider-1" }} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Route Provider" })).toBeInTheDocument());
    expect(screen.getByText("read_data")).toBeInTheDocument();
    expect(screen.getByText("provider.read")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument();
  });
});
