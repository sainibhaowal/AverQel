import { beforeEach, describe, expect, it } from "vitest";

import { MCP_ACTIVE_CONTEXT_KEY, readMCPActiveContext, saveMCPActiveContext } from "../lib/mcp-context";

describe("MCP active context", () => {
  beforeEach(() => window.localStorage.clear());

  it("stores only the active conversation context", () => {
    saveMCPActiveContext({ conversation_id: "conversation-1", deepspace_id: null });
    expect(readMCPActiveContext()).toMatchObject({ conversation_id: "conversation-1", deepspace_id: null });
    expect(window.localStorage.getItem(MCP_ACTIVE_CONTEXT_KEY)).not.toContain("token");
  });

  it("rejects stale context", () => {
    window.localStorage.setItem(MCP_ACTIVE_CONTEXT_KEY, JSON.stringify({ conversation_id: "old", updated_at: 1 }));
    expect(readMCPActiveContext()).toBeNull();
  });
});
