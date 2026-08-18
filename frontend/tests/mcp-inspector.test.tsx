import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import MCPInspector from "../app/dashboard/mcp/inspector/[id]/page";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "server-1", entryId: "provider-1" }),
}));
vi.mock("@/lib/mcp-context", () => ({
  readMCPActiveContext: () => ({ conversation_id: "conversation-1", deepspace_id: "deepspace-1" }),
}));
vi.mock("@/lib/mcp-api", () => ({
  getMCPInspector: vi.fn().mockResolvedValue({
    server: {
      id: "server-1",
      name: "Community Mail",
      status: "connected",
      transport: "streamable_http",
      provider_slug: "community-mail",
      registry_entry_id: "provider-1",
      enabled: true,
      account_identity: { email: "owner@example.com", display_name: "Owner" },
      catalog_revision: 2,
      granted_scopes: ["mail.read"],
      config: { oauth_mode: "mcp_oauth" },
    },
    diagnostics: {
      last_catalog_sync_at: "2026-07-20T00:00:00Z",
      last_error: null,
      oauth_configured: true,
      reconnect_attempts: 0,
    },
    events: [],
  }),
  getMCPPolicy: vi.fn().mockResolvedValue({
    id: "policy-1",
    tenant_id: "tenant-1",
    user_id: "user-1",
    server_id: "server-1",
    allowed_tools: [],
    denied_tools: [],
    read_only: true,
    risk_ceiling: "read",
    approval_rules: {},
    tool_modes: {},
    default_tool_mode: "needs_approval",
    default_enabled: false,
    deepspace_overrides: {},
    conversation_overrides: {},
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T00:00:00Z",
  }),
  getMCPTools: vi.fn().mockResolvedValue({
    tools: [
      {
        name: "search_mail",
        description: "Search",
        category: "Read",
        risk_labels: ["read"],
        mode: "always_allow",
      },
    ],
  }),
  getMarketplaceEntry: vi
    .fn()
    .mockResolvedValue({ id: "provider-1", requested_scopes: ["mail.read"], scope_note: null }),
  disconnectMCPServer: vi.fn(),
  refreshMCPServer: vi.fn(),
  updateMCPToolPolicy: vi.fn(),
  getMCPScopedConnections: vi.fn().mockResolvedValue({ connections: [] }),
  updateMCPScopedConnection: vi.fn(),
}));

describe("MCP inspector", () => {
  it("renders the owner-safe account, policy controls, tools, and scope controls", async () => {
    render(<MCPInspector />);
    await waitFor(() => expect(screen.getByText("owner@example.com")).toBeInTheDocument());
    expect(screen.getByText("search_mail")).toBeInTheDocument();
    expect(screen.getByText(/Individual changes override the master tool permission/i)).toBeInTheDocument();
    expect(screen.getAllByText(/DeepSpace/i).length).toBeGreaterThan(0);
  });
});
