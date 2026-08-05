import type {
  MCPConnection,
  MCPConnectionPolicy,
  MCPMarketplaceEntry,
  MCPTool,
} from "@/lib/mcp-api";

export const marketplaceEntry: MCPMarketplaceEntry = {
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
  tools: [
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
  badges: { community: true, interactive: true },
  trusted_logo_key: "unknown-provider",
  supported_products: ["Mail"],
  tool_categories: ["Communication"],
  risk_policy: {},
  health: { status: "healthy", last_checked_at: "2026-07-20T00:00:00Z" },
  requested_scopes: ["mail.read"],
  connectable: true,
};

export const policy: MCPConnectionPolicy = {
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

export const tools: MCPTool[] = [
  {
    name: "search_mail",
    description: "Search mail",
    category: "Read",
    risk_labels: ["read"],
    mode: "always_allow",
  },
  {
    name: "send_mail",
    description: "Send mail",
    category: "Email",
    risk_labels: ["external_message"],
    mode: "needs_approval",
  },
];

export const connection: MCPConnection = {
  id: "server-1",
  name: "Community Mail",
  status: "connected",
  transport: "streamable_http",
  enabled: true,
  provider_slug: "community-mail",
  account_identity: { email: "owner@example.com", display_name: "Owner" },
  granted_scopes: ["mail.read"],
  catalog_revision: 2,
  reconnect_attempts: 0,
};
