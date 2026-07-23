"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  disconnectMCPServerOAuth,
  getMarketplaceEntry,
  getMCPInspector,
  getMCPPolicy,
  getMCPTools,
  refreshMCPServer,
  startMCPServerOAuth,
  type MCPConnectionPolicy,
  type MCPInspector as MCPInspectorData,
  type MCPMarketplaceEntry,
  type MCPTool,
} from "@/lib/mcp-api";

import MCPConnectionPolicyPanel from "../../_components/MCPConnectionPolicyPanel";
import MCPConnectionScopePanel from "../../_components/MCPConnectionScopePanel";
import MCPHealthStatus from "../../_components/MCPHealthStatus";
import MCPToolPermissionTable from "../../_components/MCPToolPermissionTable";

export default function MCPInspector({ params }: { params: { id: string } }) {
  const searchParams = useSearchParams();
  const [data, setData] = useState<MCPInspectorData | null>(null);
  const [policy, setPolicy] = useState<MCPConnectionPolicy | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [provider, setProvider] = useState<MCPMarketplaceEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [inspector, connectionPolicy, catalog] = await Promise.all([getMCPInspector(params.id), getMCPPolicy(params.id), getMCPTools(params.id)]);
      const providerEntry = inspector.server.registry_entry_id ? await getMarketplaceEntry(inspector.server.registry_entry_id).catch(() => null) : null;
      setData(inspector); setPolicy(connectionPolicy); setTools(catalog.tools || []); setProvider(providerEntry); setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Inspector unavailable"); }
  }, [params.id]);

  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 10000); return () => window.clearInterval(timer); }, [load]);

  const refresh = async () => { setBusy("refresh"); try { await refreshMCPServer(params.id); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to refresh catalog."); } finally { setBusy(null); } };
  const reconnect = async () => { setBusy("reconnect"); try { const result = await startMCPServerOAuth(params.id); window.location.assign(result.authorization_url); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start reconnect."); setBusy(null); } };
  const disconnect = async () => { if (!window.confirm("Disconnect this account from AverQel?")) return; setBusy("disconnect"); try { await disconnectMCPServerOAuth(params.id); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to disconnect account."); } finally { setBusy(null); } };

  if (error && !data) return <main className="mx-auto max-w-5xl p-6"><p className="rounded border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200" role="alert">{error}</p></main>;
  if (!data || !policy) return <main className="mx-auto max-w-5xl p-6 text-sm text-white/60">Loading MCP connection…</main>;
  const server = data.server;
  const identity = server.account_identity || {};
  const config = server.config || {};

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-slate-400">MCP connection</p><h1 className="text-2xl font-semibold text-white">{server.name}</h1><p className="mt-1 text-sm text-white/55">{server.provider_slug || "Approved remote provider"} · {server.transport.replaceAll("_", " ")}</p></div><span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${server.status === "connected" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-amber-500/30 bg-amber-500/10 text-amber-300"}`}>{server.status}</span></div>
      {error && <p className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100" role="alert">{error}</p>}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Connection" value={server.enabled && server.status === "connected" ? "Enabled" : "Not active"} /><Metric label="Catalog revision" value={String(server.catalog_revision || 0)} /><Metric label="Tools" value={String(tools.length)} /><Metric label="Last refresh" value={formatDate(data.diagnostics.last_catalog_sync_at)} /></section>
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5"><div><h2 className="text-sm font-semibold uppercase tracking-wide text-white/55">Health</h2><div className="mt-3"><MCPHealthStatus health={{ status: server.status === "connected" ? "healthy" : server.status, last_checked_at: data.diagnostics.last_catalog_sync_at, detail: data.diagnostics.last_error }} /></div></div><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void refresh()} disabled={busy !== null} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-40">{busy === "refresh" ? "Refreshing…" : "Refresh catalog"}</button><button type="button" onClick={() => void reconnect()} disabled={busy !== null} className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-4 py-2 text-sm text-sky-100 hover:bg-sky-400/15 disabled:opacity-40">{busy === "reconnect" ? "Opening…" : "Reconnect"}</button><button type="button" onClick={() => void disconnect()} disabled={busy !== null} className="rounded-lg border border-red-400/25 px-4 py-2 text-sm text-red-200 hover:bg-red-400/10 disabled:opacity-40">Disconnect</button></div></section>
      {(identity.email || identity.display_name) && <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="text-lg font-semibold text-white">Connected account</h2><p className="mt-2 text-sm text-white/70">{identity.display_name || identity.email}</p>{identity.display_name && identity.email && <p className="mt-1 text-sm text-white/50">{identity.email}</p>}</section>}
      <MCPConnectionPolicyPanel serverId={server.id} policy={policy} onSaved={setPolicy} />
      <MCPToolPermissionTable serverId={server.id} tools={tools} onChanged={setTools} />
      <MCPConnectionScopePanel serverId={server.id} initialConversationId={searchParams.get("conversation_id") || ""} initialDeepSpaceId={searchParams.get("deepspace_id") || ""} />
      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="text-lg font-semibold text-white">OAuth and catalog status</h2><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><Metric label="Authentication" value={config.oauth_mode === "none" ? "Anonymous" : data.diagnostics.oauth_configured ? "OAuth connected" : "OAuth required"} /><Metric label="Requested OAuth scopes" value={provider?.requested_scopes.length ? provider.requested_scopes.join(", ") : "Managed by the provider authorization screen"} /><Metric label="Granted OAuth scopes" value={server.granted_scopes?.length ? server.granted_scopes.join(", ") : "Not yet confirmed"} /><Metric label="Reconnect attempts" value={String(data.diagnostics.reconnect_attempts)} /><Metric label="Current tool catalog" value={`${tools.length} tools at revision ${server.catalog_revision || 0}`} /></dl>{provider?.scope_note && <p className="mt-3 text-xs leading-5 text-white/45">{provider.scope_note}</p>}<p className="mt-4 text-xs leading-5 text-white/45">OAuth tokens, refresh tokens, client secrets, and raw OAuth metadata are never returned to this page. Only verified scope names, safe account labels, and catalog status are shown.</p></section>
      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="mb-3 text-lg font-semibold text-white">Recent safe events</h2><div className="space-y-2">{data.events.length === 0 ? <p className="text-sm text-white/50">No lifecycle events recorded.</p> : data.events.map((event) => <div key={`${event.sequence}-${event.event_type}`} className="flex flex-wrap justify-between gap-2 border-b border-white/5 py-2 text-sm"><span className="font-mono text-white/70">{event.event_type}</span><span className="text-xs text-white/40">#{event.sequence} · {formatDateTime(event.created_at)}</span></div>)}</div></section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3"><p className="text-xs text-white/45">{label}</p><p className="mt-1 text-sm text-white/80">{value}</p></div>; }
function formatDate(value?: string | null): string { if (!value) return "Not recorded"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "Unavailable" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date); }
function formatDateTime(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString(); }
