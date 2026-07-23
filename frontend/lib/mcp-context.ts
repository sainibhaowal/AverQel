export type MCPActiveContext = {
  conversation_id?: string | null;
  deepspace_id?: string | null;
  updated_at: number;
};

export const MCP_ACTIVE_CONTEXT_KEY = "averqel_mcp_active_context";
const MAX_CONTEXT_AGE_MS = 2 * 60 * 60 * 1000;

export function saveMCPActiveContext(context: Omit<MCPActiveContext, "updated_at">): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MCP_ACTIVE_CONTEXT_KEY, JSON.stringify({ ...context, updated_at: Date.now() }));
}

export function readMCPActiveContext(): MCPActiveContext | null {
  if (typeof window === "undefined") return null;
  try {
    const value = JSON.parse(window.localStorage.getItem(MCP_ACTIVE_CONTEXT_KEY) || "null") as Partial<MCPActiveContext> | null;
    if (!value || typeof value.updated_at !== "number" || Date.now() - value.updated_at > MAX_CONTEXT_AGE_MS) return null;
    return {
      conversation_id: typeof value.conversation_id === "string" ? value.conversation_id : null,
      deepspace_id: typeof value.deepspace_id === "string" ? value.deepspace_id : null,
      updated_at: value.updated_at,
    };
  } catch {
    return null;
  }
}
