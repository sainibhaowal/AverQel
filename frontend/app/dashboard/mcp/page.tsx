"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search } from "lucide-react";

import {
  connectMarketplaceEntry,
  deleteMCPServer,
  getMarketplace,
  getMarketplaceFacets,
  listMCPServers,
  refreshMCPServer,
  startMCPServerOAuth,
  type MCPConnection,
  type MCPMarketplaceFacets,
  type MCPMarketplaceEntry,
  type MarketplaceQuery,
} from "@/lib/mcp-api";

import MCPMarketplaceCard from "./_components/MCPMarketplaceCard";
import MCPHealthStatus from "./_components/MCPHealthStatus";

export { buildMarketplaceQuery } from "@/lib/mcp-api";

const FALLBACK_CATEGORIES = ["Productivity", "Development", "Communication", "Files", "Knowledge", "Finance", "Marketing"];

export default function MCPDashboard() {
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<"marketplace" | "installed">("marketplace");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [transport, setTransport] = useState("");
  const [official, setOfficial] = useState<boolean | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);
  const [authType, setAuthType] = useState("");
  const [trustStatus, setTrustStatus] = useState("");
  const [sort, setSort] = useState<MarketplaceQuery["sort"]>("default");
  const [facets, setFacets] = useState<MCPMarketplaceFacets>({ categories: [], transports: [], auth_types: [], trust_statuses: [] });
  const [items, setItems] = useState<MCPMarketplaceEntry[]>([]);
  const [installed, setInstalled] = useState<MCPConnection[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [callbackMessage, setCallbackMessage] = useState<string | null>(null);

  const query = useMemo(() => ({ q, category, transport, official, verified, authType, trustStatus, sort, page }), [q, category, transport, official, verified, authType, trustStatus, sort, page]);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [marketplace, servers, facetData] = await Promise.all([getMarketplace(query), listMCPServers(), getMarketplaceFacets().catch(() => null)]);
      setItems(marketplace.items || []); setTotal(marketplace.total || 0); setPages(Math.max(1, marketplace.pages || 1)); setInstalled(servers || []); if (facetData) setFacets(facetData);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "MCP marketplace unavailable"); }
    finally { setLoading(false); }
  }, [query]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const status = searchParams.get("mcp_status");
    const serverId = searchParams.get("server_id");
    if (!status) return;
    setTab(status === "connected" ? "installed" : "marketplace");
    setCallbackMessage(status === "connected" && serverId ? "MCP provider connected successfully. Open Installed to manage its account and permissions." : "MCP authorization did not complete.");
    const url = new URL(window.location.href);
    url.searchParams.delete("mcp_status");
    url.searchParams.delete("server_id");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }, [searchParams]);

  const connect = async (entry: MCPMarketplaceEntry) => {
    setError(null);
    try {
      const result = await connectMarketplaceEntry(entry.id);
      if (result.authorization_url) window.location.assign(result.authorization_url);
      else { setTab("installed"); await load(); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : `Unable to connect ${entry.name}`); }
  };

  const clearFilters = () => { setPage(1); setCategory(""); setTransport(""); setOfficial(null); setVerified(null); setAuthType(""); setTrustStatus(""); setSort("default"); };
  const categories = facets.categories.length ? facets.categories : FALLBACK_CATEGORIES;

  return (
    <main className="mx-auto min-h-screen max-w-6xl space-y-6 px-6 py-8">
      <header className="space-y-5"><div><h1 className="text-2xl font-semibold tracking-tight text-slate-100">MCP Marketplace</h1><p className="mt-1 text-sm text-slate-400">Discover approved remote connectors and control exactly what DeepSpace may use.</p></div><div className="flex gap-2"><button type="button" className={`rounded px-3 py-2 text-sm ${tab === "marketplace" ? "bg-white/15 text-white" : "border border-white/10 text-slate-300"}`} onClick={() => setTab("marketplace")}>Marketplace</button><button type="button" className={`rounded px-3 py-2 text-sm ${tab === "installed" ? "bg-white/15 text-white" : "border border-white/10 text-slate-300"}`} onClick={() => setTab("installed")}>Installed ({installed.length})</button></div>{tab === "marketplace" && <div className="space-y-3"><div className="flex flex-wrap gap-3"><label className="flex min-w-0 flex-1 items-center gap-2 rounded border border-white/10 bg-black/10 px-3 py-2"><Search className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" /><input className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500" placeholder="Search providers and tools" value={q} onChange={(event) => { setPage(1); setQ(event.target.value); }} /></label><select aria-label="Transport" className="rounded border border-white/10 bg-[#0b100d] px-3 py-2 text-sm text-slate-200" value={transport} onChange={(event) => { setPage(1); setTransport(event.target.value); }}><option value="">All transports</option>{facets.transports.map((item) => <option key={item} value={item}>{transportLabel(item)}</option>)}</select><select aria-label="Filter by" className="rounded border border-white/10 bg-[#0b100d] px-3 py-2 text-sm text-slate-200" value={authType ? `auth:${authType}` : trustStatus ? `trust:${trustStatus}` : ""} onChange={(event) => { const value = event.target.value; setPage(1); setAuthType(value.startsWith("auth:") ? value.slice(5) : ""); setTrustStatus(value.startsWith("trust:") ? value.slice(6) : ""); }}><option value="">Filter by</option>{facets.auth_types.map((item) => <option key={`auth:${item}`} value={`auth:${item}`}>{item}</option>)}{facets.trust_statuses.map((item) => <option key={`trust:${item}`} value={`trust:${item}`}>{item}</option>)}</select><select aria-label="Sort by" className="rounded border border-white/10 bg-[#0b100d] px-3 py-2 text-sm text-slate-200" value={sort} onChange={(event) => { setPage(1); setSort(event.target.value as MarketplaceQuery["sort"]); }}><option value="default">Sort by</option><option value="popular">Popular</option><option value="trending">Trending</option><option value="new">New</option><option value="alphabetical">Alphabetical</option></select><Chip label="Verified" active={verified === true} onClick={() => { setPage(1); setVerified(verified === true ? null : true); }} /></div><button type="button" className="flex w-full items-center gap-2 rounded border border-white/10 px-3 py-2 text-left text-xs text-slate-400 hover:bg-white/[0.03]" onClick={() => setFiltersOpen((open) => !open)}><span>{filtersOpen ? "▾" : "▸"}</span>More filters</button>{filtersOpen && <div className="space-y-3 rounded border border-white/10 p-3"><div className="flex flex-wrap gap-2"><Chip label="All" active={!category} onClick={() => { setPage(1); setCategory(""); }} />{categories.map((item) => <Chip key={item} label={item} active={category === item} onClick={() => { setPage(1); setCategory(item); }} />)}</div><div className="flex flex-wrap gap-2"><Chip label="Official" active={official === true} onClick={() => { setPage(1); setOfficial(official === true ? null : true); }} /><button type="button" className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-400" onClick={clearFilters}>Clear filters</button></div></div>}</div>}</header>
      {error && <p className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200" role="alert">{error}</p>}
      {callbackMessage && <p className="rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-100" role="status">{callbackMessage}</p>}
      {tab === "marketplace" ? <section className="space-y-6"><p className="text-sm text-slate-400">{total.toLocaleString()} approved connectors</p>{loading ? <p className="text-sm text-white/60">Loading marketplace…</p> : items.length === 0 ? <p className="rounded-2xl border border-white/10 p-6 text-sm text-white/55">No approved connectors match these filters.</p> : <div className="grid gap-4 md:grid-cols-2">{items.map((entry) => { const connectedServer = installed.find((server) => server.registry_entry_id === entry.id || (server.provider_slug && server.provider_slug === entry.provider_slug)); return <MCPMarketplaceCard key={entry.id} entry={entry} connectedServer={connectedServer} onConnect={(value) => void connect(value)} onReconnect={(server) => { void startMCPServerOAuth(server.id).then((result) => window.location.assign(result.authorization_url)).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to reconnect provider.")); }} />; })}</div>}<Pagination page={page} hasNext={page < pages} onPrevious={() => setPage(Math.max(1, page - 1))} onNext={() => setPage(page + 1)} /></section> : <section className="grid gap-4">{installed.length === 0 ? <p className="rounded-2xl border border-white/10 p-6 text-sm text-white/55">No MCP connections yet. Connect one from the marketplace.</p> : installed.map((server) => <InstalledCard key={server.id} server={server} onRefresh={async () => { await refreshMCPServer(server.id); await load(); }} onDisconnect={async () => { if (window.confirm("Disconnect this MCP connection?")) { await deleteMCPServer(server.id); await load(); } }} />)}</section>}
    </main>
  );
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) { return <button type="button" className={`rounded-full border px-3 py-1.5 text-xs transition ${active ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-100" : "border-white/10 bg-white/5 text-white/65 hover:bg-white/10"}`} onClick={onClick}>{label}</button>; }

function InstalledCard({ server, onRefresh, onDisconnect }: { server: MCPConnection; onRefresh: () => Promise<void>; onDisconnect: () => Promise<void> }) {
  const config = server.config || {};
  const statusTone = server.status === "connected" ? "text-emerald-300 border-emerald-500/30 bg-emerald-500/10" : server.status === "failed" ? "text-red-300 border-red-500/30 bg-red-500/10" : "text-amber-300 border-amber-500/30 bg-amber-500/10";
  return <article className="rounded-2xl border border-white/10 bg-white/[0.04] p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-lg font-semibold text-white">{server.name}</h2><p className="mt-1 text-sm text-white/60">{transportLabel(server.transport)} · {server.config?.oauth_mode === "none" ? "Anonymous" : "OAuth"} · {Number(config.mcp_catalog_tool_count || 0)} tools</p><p className="mt-1 text-xs text-white/45">Catalog revision {server.catalog_revision || 0}{config.mcp_catalog_last_sync_at ? ` · Last refreshed ${formatRelative(config.mcp_catalog_last_sync_at)}` : ""}</p>{server.account_identity?.email && <p className="mt-2 text-sm text-white/75">Connected account: {server.account_identity.email}</p>}</div><span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${statusTone}`}>{server.status}</span></div><div className="mt-4"><MCPHealthStatus health={{ status: server.status === "connected" ? "healthy" : server.status, last_checked_at: config.mcp_catalog_last_sync_at }} compact /></div><div className="mt-4 flex flex-wrap gap-2"><a href={`/dashboard/mcp/inspector/${encodeURIComponent(server.id)}`} className="rounded-xl border border-white/10 px-4 py-2 text-sm text-white/80 hover:bg-white/10">Manage connection</a><button type="button" className="rounded-xl border border-white/10 px-4 py-2 text-sm text-white/80 hover:bg-white/10" onClick={() => void onRefresh()}>Refresh catalog</button><button type="button" className="rounded-xl border border-red-400/20 px-4 py-2 text-sm text-red-200 hover:bg-red-400/10" onClick={() => void onDisconnect()}>Disconnect</button></div></article>;
}

function Pagination({ page, hasNext, onPrevious, onNext }: { page: number; hasNext: boolean; onPrevious: () => void; onNext: () => void }) { return <div className="flex items-center justify-end gap-2"><button type="button" disabled={page <= 1} onClick={onPrevious} className="rounded border border-white/10 px-3 py-2 text-xs text-white/70 disabled:opacity-30">Previous</button><span className="text-xs text-white/45">Page {page}</span><button type="button" disabled={!hasNext} onClick={onNext} className="rounded border border-white/10 px-3 py-2 text-xs text-white/70 disabled:opacity-30">Next</button></div>; }

function transportLabel(value?: string | null): string { switch (value) { case "streamable_http": return "Remote HTTP"; case "sse": return "Remote SSE"; case "stdio": return "Local stdio"; case "ssh": return "Remote SSH"; default: return value ? value.replaceAll("_", " ") : "Remote"; } }
function formatRelative(value?: string | null): string { if (!value) return "unknown"; const date = new Date(value); if (Number.isNaN(date.getTime())) return "unknown"; const days = Math.round((date.getTime() - Date.now()) / 86400000); return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(days, "day"); }
