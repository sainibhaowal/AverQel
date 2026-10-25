import { fetchWithAuth } from "@/lib/api";

export type MCPRiskLabel = "read" | "write" | "delete" | "external_message";
export type MCPToolMode = "always_allow" | "needs_approval" | "blocked";
export type MCPTransport = "streamable_http" | "sse" | "stdio" | "ssh" | string;

export type MCPHealth = {
  status: string;
  last_checked_at?: string | null;
  detail?: string | null;
};

export type MCPMarketplaceTool = {
  name: string;
  description?: string | null;
  category?: string | null;
  risk_labels: string[];
};

export type MCPMarketplaceEntry = {
  id: string;
  name: string;
  version?: string | null;
  server_name?: string;
  publisher?: string | null;
  description?: string | null;
  transport?: MCPTransport | null;
  remote_url?: string | null;
  categories: string[];
  official: boolean;
  verified: boolean;
  source: string;
  action: "connect" | "install";
  tool_count: number;
  last_catalog_sync_at?: string | null;
  last_seen_at?: string | null;
  docs_url?: string | null;
  logo_url?: string | null;
  capabilities: string[];
  tool_preview: MCPMarketplaceTool[];
  tools?: MCPMarketplaceTool[];
  catalog_status: string;
  auth_type: string;
  trust_status: string;
  verification_source?: string | null;
  popularity_rank?: number | null;
  provider_slug?: string | null;
  publisher_type?: "official" | "community" | null;
  author_name?: string | null;
  author_website_url?: string | null;
  support_url?: string | null;
  privacy_policy_url?: string | null;
  badges: Record<string, boolean>;
  availability?: string | null;
  trusted_logo_key?: string | null;
  supported_products: string[];
  tool_categories: string[];
  risk_policy: Record<string, unknown>;
  health: MCPHealth;
  reviewed_at?: string | null;
  review_due_at?: string | null;
  requested_scopes: string[];
  scope_mode?: string | null;
  scope_note?: string | null;
  connectable: boolean;
  connectability_reason?: string | null;
};

export type MCPMarketplacePage = {
  items: MCPMarketplaceEntry[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};

export type MCPMarketplaceFacets = {
  categories: string[];
  transports: string[];
  auth_types: string[];
  trust_statuses: string[];
};

export type MCPComposioStatus = {
  configured: boolean;
  oauth_callback_ready: boolean;
};

export type MCPComposioToolkit = {
  slug: string;
  name: string;
  description: string;
  logo_url?: string | null;
  app_url?: string | null;
  auth_guide_url?: string | null;
  version?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  categories: string[];
  tool_count: number;
  auth_schemes: string[];
  no_auth: boolean;
};

export type MCPComposioToolkitPage = {
  items: MCPComposioToolkit[];
  next_cursor?: string | null;
  current_page: number;
  total_items: number;
};

export type MCPComposioTool = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  risk_labels: string[];
  version?: string | null;
};

export type MCPComposioToolkitDetail = MCPComposioToolkit & {
  tools: MCPComposioTool[];
  tools_loaded: number;
  tools_next_cursor?: string | null;
};

export type MCPSafeAccountIdentity = {
  email?: string;
  display_name?: string;
  provider_subject?: string;
  account_id?: string;
  identity_source?: string;
};

export type MCPSafeConfig = {
  server_url?: string;
  oauth_mode?: string;
  auth_type?: string;
  transport?: string;
  provider_slug?: string;
  vendor_slug?: string;
  source?: string;
  categories?: string[];
  mcp_catalog_tool_count?: number;
  mcp_catalog_last_sync_at?: string | null;
  catalog_revision?: number;
};

export type MCPConnectionPolicy = {
  id: string;
  tenant_id: string;
  user_id: string;
  server_id: string;
  allowed_tools: string[];
  denied_tools: string[];
  read_only: boolean;
  risk_ceiling: MCPRiskLabel;
  approval_rules: Record<string, MCPToolMode>;
  tool_modes: Record<string, MCPToolMode>;
  default_tool_mode: MCPToolMode;
  default_enabled: boolean;
  deepspace_overrides: Record<string, boolean>;
  conversation_overrides: Record<string, boolean>;
  created_at: string;
  updated_at: string;
};

export type MCPConnection = {
  id: string;
  name: string;
  transport: MCPTransport;
  config?: MCPSafeConfig;
  enabled: boolean;
  registry_entry_id?: string | null;
  provider_slug?: string | null;
  account_identity: MCPSafeAccountIdentity;
  granted_scopes?: string[];
  connection_policy_id?: string | null;
  catalog_revision: number;
  status: string;
  last_error?: string | null;
  reconnect_attempts: number;
  policy?: MCPConnectionPolicy | null;
};

export type MCPTool = {
  name: string;
  description?: string | null;
  category?: string | null;
  risk_labels: string[];
  mode: MCPToolMode;
};

export type MCPToolCatalog = {
  server_id: string;
  catalog_revision: number;
  tools: MCPTool[];
};

export type MCPScope = "deepspace" | "conversation";

export type MCPScopedConnectionList = {
  scope: MCPScope;
  scope_id: string;
  connections: Array<{ server: MCPConnection; enabled: boolean }>;
};

export type MCPInspector = {
  server: MCPConnection;
  diagnostics: {
    credential_configured: boolean;
    oauth_configured: boolean;
    reconnect_attempts: number;
    last_error?: string | null;
    last_catalog_sync_at?: string | null;
    active_tools: Array<{
      name: string;
      description?: string | null;
      input_schema?: unknown;
    }>;
  };
  events: Array<{
    event_type: string;
    sequence: number;
    created_at: string;
    tool?: string | null;
    error_code?: string | null;
    content_item_count?: number | null;
    is_error?: boolean | null;
  }>;
};

export type MarketplaceQuery = {
  q: string;
  category: string;
  transport: string;
  official?: boolean | null;
  verified?: boolean | null;
  authType?: string;
  trustStatus?: string;
  sort?: "default" | "popular" | "trending" | "new" | "alphabetical";
  page: number;
};

export function buildMarketplaceQuery(params: MarketplaceQuery): string {
  const query = new URLSearchParams();
  if (params.q.trim()) query.set("q", params.q.trim());
  if (params.category) query.set("category", params.category);
  if (params.transport) query.set("transport", params.transport);
  if (params.official !== undefined && params.official !== null)
    query.set("official", String(params.official));
  if (params.verified !== undefined && params.verified !== null)
    query.set("verified", String(params.verified));
  if (params.authType) query.set("auth_type", params.authType);
  if (params.trustStatus) query.set("trust_status", params.trustStatus);
  if (params.sort && params.sort !== "default") query.set("sort", params.sort);
  query.set("page", String(params.page));
  return `/mcp/marketplace?${query.toString()}`;
}

export function safeExternalUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if ((url.protocol !== "https:" && url.protocol !== "http:") || url.username || url.password)
      return null;
    return url.toString();
  } catch {
    return null;
  }
}

type MCPRequestOptions = RequestInit & {
  timeoutMs?: number;
  silentTimeout?: boolean;
};

async function request<T>(path: string, init?: MCPRequestOptions): Promise<T> {
  const response = await fetchWithAuth(path, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "MCP request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getMarketplace(query: MarketplaceQuery): Promise<MCPMarketplacePage> {
  return request<MCPMarketplacePage>(buildMarketplaceQuery(query));
}

export function getMarketplaceFacets(): Promise<MCPMarketplaceFacets> {
  return request<MCPMarketplaceFacets>("/mcp/marketplace/facets");
}

export function getMarketplaceEntry(entryId: string): Promise<MCPMarketplaceEntry> {
  return request<MCPMarketplaceEntry>(`/mcp/marketplace/${encodeURIComponent(entryId)}`);
}

export function getComposioStatus(
  options: Pick<MCPRequestOptions, "signal"> = {},
): Promise<MCPComposioStatus> {
  return request<MCPComposioStatus>("/mcp/composio/status", {
    ...options,
    timeoutMs: 20_000,
    silentTimeout: true,
  });
}

export function saveComposioApiKey(apiKey: string): Promise<MCPComposioStatus> {
  return request<MCPComposioStatus>("/mcp/composio/credential", {
    method: "PUT",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function removeComposioApiKey(): Promise<void> {
  return request<void>("/mcp/composio/credential", { method: "DELETE" });
}

export function getComposioToolkits(
  params: {
    q?: string;
    category?: string;
    cursor?: string | null;
    limit?: number;
  } = {},
  options: Pick<MCPRequestOptions, "signal"> = {},
): Promise<MCPComposioToolkitPage> {
  const query = new URLSearchParams();
  if (params.q?.trim()) query.set("q", params.q.trim());
  if (params.category) query.set("category", params.category);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));
  return request<MCPComposioToolkitPage>(`/mcp/composio/toolkits?${query.toString()}`, {
    ...options,
    timeoutMs: 20_000,
    silentTimeout: true,
  });
}

export function getComposioToolkit(
  slug: string,
  cursor?: string | null,
  options: Pick<MCPRequestOptions, "signal"> = {},
): Promise<MCPComposioToolkitDetail> {
  const query = new URLSearchParams();
  if (cursor) query.set("cursor", cursor);
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<MCPComposioToolkitDetail>(
    `/mcp/composio/toolkits/${encodeURIComponent(slug)}${suffix}`,
    { ...options, timeoutMs: 20_000, silentTimeout: true },
  );
}

export function connectComposioToolkit(slug: string): Promise<{
  server: MCPConnection;
  authorization_url?: string | null;
  already_connected: boolean;
  authorization_required: boolean;
}> {
  return request(`/mcp/composio/toolkits/${encodeURIComponent(slug)}/connect`, {
    method: "POST",
  });
}

export function completeComposioOAuth(input: {
  toolkitSlug: string;
  connectedAccountId: string;
  status: "success" | "failed";
}): Promise<{ status: "connecting" | "failed"; server_id: string }> {
  return request("/mcp/composio/oauth/complete", {
    method: "POST",
    body: JSON.stringify({
      toolkit_slug: input.toolkitSlug,
      connected_account_id: input.connectedAccountId,
      status: input.status,
    }),
  });
}

export function connectMarketplaceEntry(
  entryId: string,
): Promise<{ server: MCPConnection; authorization_url?: string | null; setup_required?: boolean }> {
  return request(`/mcp/marketplace/${encodeURIComponent(entryId)}/connect`, { method: "POST" });
}

export function listMCPServers(): Promise<MCPConnection[]> {
  return request<MCPConnection[]>("/mcp/servers");
}

export function getMCPServer(serverId: string): Promise<MCPConnection> {
  return request<MCPConnection>(`/mcp/servers/${encodeURIComponent(serverId)}`);
}

export function deleteMCPServer(serverId: string): Promise<void> {
  return request<void>(`/mcp/servers/${encodeURIComponent(serverId)}`, { method: "DELETE" });
}

export function getMCPPolicy(serverId: string): Promise<MCPConnectionPolicy> {
  return request<MCPConnectionPolicy>(`/mcp/servers/${encodeURIComponent(serverId)}/policy`);
}

export function updateMCPPolicy(
  serverId: string,
  policy: Omit<
    MCPConnectionPolicy,
    "id" | "tenant_id" | "user_id" | "server_id" | "created_at" | "updated_at"
  >,
): Promise<MCPConnectionPolicy> {
  return request<MCPConnectionPolicy>(`/mcp/servers/${encodeURIComponent(serverId)}/policy`, {
    method: "PUT",
    body: JSON.stringify(policy),
  });
}

export function getMCPTools(serverId: string): Promise<MCPToolCatalog> {
  return request<MCPToolCatalog>(`/mcp/servers/${encodeURIComponent(serverId)}/tools`);
}

export function updateMCPToolPolicy(
  serverId: string,
  toolName: string,
  mode: MCPToolMode,
): Promise<MCPTool> {
  return request<MCPTool>(
    `/mcp/servers/${encodeURIComponent(serverId)}/tools/${encodeURIComponent(toolName)}/policy`,
    {
      method: "PUT",
      body: JSON.stringify({ mode }),
    },
  );
}

export function getMCPScopedConnections(
  scope: MCPScope,
  scopeId: string,
): Promise<MCPScopedConnectionList> {
  return request<MCPScopedConnectionList>(
    `/mcp/${scope === "deepspace" ? "deepspaces" : "conversations"}/${encodeURIComponent(scopeId)}/connections`,
  );
}

export function updateMCPScopedConnection(
  scope: MCPScope,
  scopeId: string,
  serverId: string,
  enabled: boolean,
): Promise<unknown> {
  return request(
    `/mcp/${scope === "deepspace" ? "deepspaces" : "conversations"}/${encodeURIComponent(scopeId)}/connections/${encodeURIComponent(serverId)}`,
    {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    },
  );
}

export function refreshMCPServer(serverId: string): Promise<{ status: string; server_id: string }> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}/refresh`, { method: "POST" });
}

export function startMCPServerOAuth(serverId: string): Promise<{ authorization_url: string }> {
  return request(`/mcp/servers/${encodeURIComponent(serverId)}/oauth/start`, { method: "POST" });
}

export function disconnectMCPServerOAuth(serverId: string): Promise<void> {
  return request<void>(`/mcp/servers/${encodeURIComponent(serverId)}/oauth`, { method: "DELETE" });
}

export function getMCPInspector(serverId: string): Promise<MCPInspector> {
  return request<MCPInspector>(`/mcp/servers/${encodeURIComponent(serverId)}/inspector`);
}
