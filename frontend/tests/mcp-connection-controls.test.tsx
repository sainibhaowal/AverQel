import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MCPConnectionPolicy, MCPMarketplaceEntry, MCPTool } from "@/lib/mcp-api";
import MCPConnectionPolicyPanel from "../app/dashboard/mcp/_components/MCPConnectionPolicyPanel";
import MCPProviderDetails from "../app/dashboard/mcp/_components/MCPProviderDetails";
import MCPToolPermissionTable from "../app/dashboard/mcp/_components/MCPToolPermissionTable";

const { updateMCPPolicyMock, updateMCPToolPolicyMock } = vi.hoisted(() => ({
  updateMCPPolicyMock: vi.fn(),
  updateMCPToolPolicyMock: vi.fn(),
}));

vi.mock("@/lib/mcp-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/mcp-api")>("@/lib/mcp-api");
  return {
    ...actual,
    updateMCPPolicy: updateMCPPolicyMock,
    updateMCPToolPolicy: updateMCPToolPolicyMock,
  };
});

const entry: MCPMarketplaceEntry = {
  id: "provider-1",
  name: "Community Mail",
  version: "1.2.3",
  publisher: "Community Publisher",
  description: "Read and organize mail.",
  transport: "streamable_http",
  remote_url: "https://provider.example/mcp",
  categories: ["Communication"],
  official: false,
  verified: true,
  source: "curated",
  action: "connect",
  tool_count: 2,
  capabilities: ["search_mail"],
  tool_preview: [
    { name: "search_mail", description: "Search mail", category: "Read", risk_labels: ["read"] },
  ],
  catalog_status: "ready",
  auth_type: "oauth",
  trust_status: "approved",
  publisher_type: "community",
  author_name: "Community Publisher",
  author_website_url: "https://provider.example",
  docs_url: "https://provider.example/docs",
  support_url: "https://provider.example/support",
  privacy_policy_url: "https://provider.example/privacy",
  badges: { community: true },
  trusted_logo_key: "unknown-provider",
  supported_products: ["Mail"],
  tool_categories: ["Communication"],
  risk_policy: {},
  health: { status: "healthy", last_checked_at: "2026-07-20T00:00:00Z" },
  requested_scopes: ["mail.read"],
  connectable: true,
};

const policy: MCPConnectionPolicy = {
  id: "policy-1",
  tenant_id: "tenant-1",
  user_id: "user-1",
  server_id: "server-1",
  allowed_tools: [],
  denied_tools: [],
  read_only: true,
  risk_ceiling: "read",
  approval_rules: {
    write: "needs_approval",
    delete: "needs_approval",
    external_message: "needs_approval",
  },
  tool_modes: {},
  default_enabled: false,
  deepspace_overrides: {},
  conversation_overrides: {},
  created_at: "2026-07-20T00:00:00Z",
  updated_at: "2026-07-20T00:00:00Z",
};

const tools: MCPTool[] = [
  {
    name: "search_mail",
    description: "Search mail",
    category: "Read",
    risk_labels: ["read"],
    mode: "always_allow",
  },
];

describe("MCP connection controls", () => {
  beforeEach(() => {
    updateMCPPolicyMock.mockReset();
    updateMCPPolicyMock.mockResolvedValue(policy);
    updateMCPToolPolicyMock.mockReset();
    updateMCPToolPolicyMock.mockImplementation(
      async (_server: string, name: string, mode: string) => ({ ...tools[0], name, mode }),
    );
  });

  it("renders community trust warning, safe links, scopes, and health without remote probing", () => {
    render(<MCPProviderDetails entry={entry} onConnect={vi.fn()} />);
    expect(screen.getByRole("note")).toHaveTextContent(/reviewed community connector/i);
    expect(screen.getByText("mail.read")).toBeInTheDocument();
    expect(screen.getByText("https://provider.example/mcp")).toBeInTheDocument();
    expect(screen.getByText("1.2.3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /documentation/i })).toHaveAttribute(
      "href",
      "https://provider.example/docs",
    );
    expect(screen.getByText("Healthy")).toBeInTheDocument();
  });

  it("renders the complete reviewed tool field and rejects unsafe remote logos", () => {
    render(
      <MCPProviderDetails
        entry={{
          ...entry,
          tools: [
            {
              name: "create_draft",
              description: "Create a draft",
              category: "Email",
              risk_labels: ["write"],
            },
          ],
          logo_url: "javascript:alert(1)",
        }}
        onConnect={vi.fn()}
      />,
    );
    expect(screen.getByText("create_draft")).toBeInTheDocument();
    expect(screen.getByText("write")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("updates a tool permission through the typed API boundary", async () => {
    render(<MCPToolPermissionTable serverId="server-1" tools={tools} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Permission for search_mail" }), {
      target: { value: "blocked" },
    });
    await waitFor(() =>
      expect(updateMCPToolPolicyMock).toHaveBeenCalledWith("server-1", "search_mail", "blocked"),
    );
  });

  it("saves conservative connection policy settings", async () => {
    render(<MCPConnectionPolicyPanel serverId="server-1" policy={policy} />);
    fireEvent.click(screen.getAllByRole("checkbox")[0]!);
    fireEvent.click(screen.getByRole("button", { name: "Save policy" }));
    await waitFor(() =>
      expect(updateMCPPolicyMock).toHaveBeenCalledWith(
        "server-1",
        expect.objectContaining({ default_enabled: true, read_only: true, risk_ceiling: "read" }),
      ),
    );
    expect(
      screen.getByText(/available automatically in every DeepSpace conversation/i),
    ).toBeInTheDocument();
  });
});
