import { useCallback, useEffect, useState } from "react";

import { getMCPScopedConnections, updateMCPScopedConnection, type MCPConnection, type MCPScope } from "@/lib/mcp-api";

export default function MCPConnectionScopePanel({ serverId, initialConversationId = "", initialDeepSpaceId = "" }: { serverId: string; initialConversationId?: string; initialDeepSpaceId?: string }) {
  const [conversationId, setConversationId] = useState(initialConversationId);
  const [deepSpaceId, setDeepSpaceId] = useState(initialDeepSpaceId);
  const [conversation, setConversation] = useState<{ server: MCPConnection; enabled: boolean } | null>(null);
  const [deepSpace, setDeepSpace] = useState<{ server: MCPConnection; enabled: boolean } | null>(null);
  const [loading, setLoading] = useState<MCPScope | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadScope = useCallback(async (scope: MCPScope, scopeId: string) => {
    if (!scopeId.trim()) return;
    setLoading(scope); setMessage(null);
    try { const result = await getMCPScopedConnections(scope, scopeId.trim()); const current = result.connections.find((item) => item.server.id === serverId) || null; if (scope === "conversation") setConversation(current); else setDeepSpace(current); }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : "Unable to load scope."); }
    finally { setLoading(null); }
  }, [serverId]);

  useEffect(() => { if (initialConversationId) void loadScope("conversation", initialConversationId); if (initialDeepSpaceId) void loadScope("deepspace", initialDeepSpaceId); }, [initialConversationId, initialDeepSpaceId, loadScope]);

  async function toggle(scope: MCPScope, scopeId: string, enabled: boolean) {
    setLoading(scope); setMessage(null);
    try { await updateMCPScopedConnection(scope, scopeId.trim(), serverId, enabled); await loadScope(scope, scopeId); }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : "Unable to update scope."); setLoading(null); }
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><div><h2 className="text-lg font-semibold text-white">DeepSpace and conversation access</h2><p className="mt-1 text-sm text-white/55">Connections are disabled for each scope unless you explicitly enable them. AverQel verifies ownership server-side.</p></div>{message && <p className="mt-3 text-sm text-amber-200" role="status">{message}</p>}<div className="mt-5 grid gap-4 lg:grid-cols-2"><ScopeControl label="Conversation ID" value={conversationId} onChange={setConversationId} scope="conversation" current={conversation} loading={loading === "conversation"} onLoad={() => void loadScope("conversation", conversationId)} onToggle={(enabled) => void toggle("conversation", conversationId, enabled)} /><ScopeControl label="DeepSpace ID" value={deepSpaceId} onChange={setDeepSpaceId} scope="deepspace" current={deepSpace} loading={loading === "deepspace"} onLoad={() => void loadScope("deepspace", deepSpaceId)} onToggle={(enabled) => void toggle("deepspace", deepSpaceId, enabled)} /></div><p className="mt-4 text-xs leading-5 text-white/40">Use an ID from the current tenant. Invalid or cross-tenant IDs are rejected, and stale or missing overrides remain disabled.</p></section>
  );
}

function ScopeControl({ label, value, onChange, scope, current, loading, onLoad, onToggle }: { label: string; value: string; onChange: (value: string) => void; scope: MCPScope; current: { server: MCPConnection; enabled: boolean } | null; loading: boolean; onLoad: () => void; onToggle: (enabled: boolean) => void }) {
  return <div className="rounded-xl border border-white/10 p-4"><label className="block text-sm text-white">{label}<input value={value} onChange={(event) => onChange(event.target.value)} placeholder={`Enter ${scope} ID`} className="mt-2 w-full rounded-lg border border-white/10 bg-[#111512] px-3 py-2 font-mono text-xs text-white placeholder:text-white/25" /></label><div className="mt-3 flex items-center justify-between gap-3"><button type="button" onClick={onLoad} disabled={loading || !value.trim()} className="rounded-lg border border-white/10 px-3 py-2 text-xs text-white/75 hover:bg-white/10 disabled:opacity-40">{loading ? "Loading…" : "Load scope"}</button>{current && <label className="flex items-center gap-2 text-xs text-white/65"><input type="checkbox" checked={current.enabled} disabled={loading} onChange={(event) => onToggle(event.target.checked)} />Enabled for this {scope === "deepspace" ? "DeepSpace" : "conversation"}</label>}</div></div>;
}
