"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Search, X } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";

type MarketplaceEntry = {
  id: string;
  name: string;
  publisher?: string;
  description?: string;
  transport?: string;
  remote_url?: string;
  categories?: string[];
  official: boolean;
  verified: boolean;
  source?: string;
  oauth_requirements?: Record<string, unknown>;
  action: string;
  logo_url?: string | null;
  tool_count?: number;
  last_seen_at?: string | null;
  capabilities?: string[];
  docs_url?: string | null;
  connection_options?: Array<Record<string, unknown>>;
  tool_preview?: Array<{ name: string; description?: string; inputSchema?: Record<string, unknown> }>;
  catalog_status?: string;
  auth_type?: string;
  trust_status?: string;
  verification_source?: string | null;
  popularity_rank?: number | null;
  connectable?: boolean;
  connectability_reason?: string | null;
};

type InstalledServer = {
  id: string;
  name: string;
  status: string;
  transport: string;
  config: Record<string, unknown>;
  last_error?: string | null;
};

type MarketplaceQuery = {
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

type MarketplaceFacets = {
  categories: string[];
  transports: string[];
  auth_types: string[];
  trust_statuses: string[];
};

export const CATEGORY_OPTIONS = [
  "Productivity",
  "Development",
  "Communication",
  "Files",
  "Knowledge",
  "Finance",
  "Marketing",
] as const;

export function buildMarketplaceQuery(params: MarketplaceQuery): string {
  const query = new URLSearchParams();
  if (params.q.trim()) query.set("q", params.q.trim());
  if (params.category) query.set("category", params.category);
  if (params.transport) query.set("transport", params.transport);
  if (params.official !== undefined && params.official !== null) query.set("official", String(params.official));
  if (params.verified !== undefined && params.verified !== null) query.set("verified", String(params.verified));
  if (params.authType) query.set("auth_type", params.authType);
  if (params.trustStatus) query.set("trust_status", params.trustStatus);
  if (params.sort && params.sort !== "default") query.set("sort", params.sort);
  query.set("page", String(params.page));
  return `/mcp/marketplace?${query.toString()}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "Unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function formatRelative(value?: string | null): string {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const days = Math.round((date.getTime() - Date.now()) / 86400000);
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(days, "day");
}

function capabilities(entry: MarketplaceEntry): string[] {
  return Array.isArray(entry.capabilities) ? entry.capabilities.map(String).filter(Boolean) : [];
}

function authLabel(entry: MarketplaceEntry): string {
  if (entry.auth_type === "anonymous") return "Anonymous";
  if (entry.auth_type === "oauth") return "OAuth";
  const requirements = entry.oauth_requirements || {};
  if (Object.keys(requirements).length === 0) return "Anonymous";
  return "OAuth";
}

function statusTone(status: string): { label: string; className: string } {
  switch (status) {
    case "connected": return { label: "CONNECTED", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" };
    case "needs_auth": return { label: "NEEDS AUTH", className: "border-amber-500/30 bg-amber-500/10 text-amber-300" };
    case "failed": return { label: "FAILED", className: "border-red-500/30 bg-red-500/10 text-red-300" };
    default: return { label: "DISCONNECTED", className: "border-slate-500/30 bg-slate-500/10 text-slate-300" };
  }
}

export default function MCPDashboard() {
  const [tab, setTab] = useState<"marketplace" | "installed">("marketplace");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [transport, setTransport] = useState("");
  const [official, setOfficial] = useState<boolean | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);
  const [authType, setAuthType] = useState("");
  const [trustStatus, setTrustStatus] = useState("");
  const [sort, setSort] = useState<MarketplaceQuery["sort"]>("default");
  const [facets, setFacets] = useState<MarketplaceFacets>({ categories: [], transports: [], auth_types: [], trust_statuses: [] });
  const [items, setItems] = useState<MarketplaceEntry[]>([]);
  const [installed, setInstalled] = useState<InstalledServer[]>([]);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<MarketplaceEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const marketplaceQuery = useMemo(() => buildMarketplaceQuery({ q, category, transport, official, verified, authType, trustStatus, sort, page }), [q, category, transport, official, verified, authType, trustStatus, sort, page]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [marketplaceResponse, serversResponse, facetsResponse] = await Promise.all([
        fetchWithAuth(marketplaceQuery),
        fetchWithAuth("/mcp/servers"),
        fetchWithAuth("/mcp/marketplace/facets"),
      ]);
      if (!marketplaceResponse.ok) throw new Error("Marketplace unavailable");
      if (!serversResponse.ok) throw new Error("Installed MCP servers unavailable");
      const marketplace = await marketplaceResponse.json() as { items: MarketplaceEntry[]; total: number; pages?: number };
      setItems(marketplace.items || []);
      setTotal(marketplace.total || 0);
      setPages(Math.max(1, Number(marketplace.pages || 1)));
      setInstalled(await serversResponse.json() as InstalledServer[]);
      if (facetsResponse?.ok) setFacets(await facetsResponse.json() as MarketplaceFacets);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "MCP marketplace unavailable");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [marketplaceQuery]);

  const connect = async (entry: MarketplaceEntry) => {
    setError(null);
    const response = await fetchWithAuth(`/mcp/marketplace/${entry.id}/connect`, {
      method: "POST",
    });
    if (!response.ok) {
      setError((await response.json().catch(() => null))?.detail || `Unable to connect ${entry.name}`);
      return;
    }
    const result = await response.json() as { authorization_url?: string };
    if (result.authorization_url) window.location.assign(result.authorization_url);
    else await load();
  };

  const clearFilters = () => {
    setPage(1);
    setCategory("");
    setTransport("");
    setOfficial(null);
    setVerified(null);
    setAuthType("");
    setTrustStatus("");
    setSort("default");
  };

  return (
    <main className="mx-auto min-h-screen max-w-5xl space-y-6 px-6 py-10">
      <header className="space-y-5">
        <div className="flex items-start justify-between gap-5">
          <div><h1 className="text-2xl font-semibold tracking-tight text-slate-100">MCP Marketplace</h1><p className="text-sm text-slate-400">Discover and connect official MCP applications.</p></div>
        </div>
        <div className="flex gap-2"><button className={`rounded px-3 py-2 text-sm ${tab === "marketplace" ? "bg-white/15 text-white" : "border border-white/10 text-slate-300"}`} onClick={() => setTab("marketplace")}>Marketplace</button><button className={`rounded px-3 py-2 text-sm ${tab === "installed" ? "bg-white/15 text-white" : "border border-white/10 text-slate-300"}`} onClick={() => setTab("installed")}>Installed ({installed.length})</button></div>
        {tab === "marketplace" && <>
          <div className="flex flex-wrap gap-3">
            <label className="flex min-w-0 flex-1 items-center gap-2 rounded border border-white/10 bg-black/10 px-3 py-2"><Search className="h-3.5 w-3.5 text-slate-500" /><input className="w-full bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500" placeholder="Search official apps, tools, vendors..." value={q} onChange={(event) => { setPage(1); setQ(event.target.value); }} /></label>
            <select aria-label="Transport" className="rounded border border-white/10 bg-[#0b100d] px-3 py-2 text-sm text-slate-200" value={transport} onChange={(event) => { setPage(1); setTransport(event.target.value); }}><option value="">All transports</option>{facets.transports.map((item) => <option key={item} value={item}>{item === "streamable_http" ? "Remote HTTP" : item.toUpperCase()}</option>)}</select>
            <select aria-label="Filter by" className="rounded border border-white/10 bg-[#0b100d] px-3 py-2 text-sm text-slate-200" value={authType ? `auth:${authType}` : trustStatus ? `trust:${trustStatus}` : ""} onChange={(event) => { const value = event.target.value; setPage(1); setAuthType(value.startsWith("auth:") ? value.slice(5) : ""); setTrustStatus(value.startsWith("trust:") ? value.slice(6) : ""); }}><option value="">Filter by</option>{facets.auth_types.map((item) => <option key={`auth:${item}`} value={`auth:${item}`}>{item}</option>)}{facets.trust_statuses.map((item) => <option key={`trust:${item}`} value={`trust:${item}`}>{item}</option>)}</select>
            <select aria-label="Sort by" className="rounded border border-white/10 bg-[#0b100d] px-3 py-2 text-sm text-slate-200" value={sort} onChange={(event) => { setPage(1); setSort(event.target.value as MarketplaceQuery["sort"]); }}><option value="default">Sort by</option><option value="popular">Popular</option><option value="trending">Trending</option><option value="new">New</option><option value="alphabetical">Alphabetical</option></select>
            <Chip label="Verified" active={verified === true} onClick={() => { setPage(1); setVerified(verified === true ? null : true); }} />
          </div>
          <button className="flex w-full items-center gap-2 rounded border border-white/10 px-3 py-2 text-left text-xs text-slate-400 hover:bg-white/[0.03]" onClick={() => setFiltersOpen((open) => !open)}><span>{filtersOpen ? "▾" : "▸"}</span>More filters and install options</button>
          {filtersOpen && <div className="space-y-3 rounded border border-white/10 p-3"><div className="flex flex-wrap gap-2"><Chip label="All" active={!category} onClick={() => { setPage(1); setCategory(""); }} />{CATEGORY_OPTIONS.map((item) => <Chip key={item} label={item} active={category === item} onClick={() => { setPage(1); setCategory(item); }} />)}</div><div className="flex flex-wrap gap-2"><Chip label="Official" active={official === true} onClick={() => { setPage(1); setOfficial(official === true ? null : true); }} /><Chip label="Remote" active={!transport || transport === "streamable_http" || transport === "sse"} onClick={() => { setPage(1); setTransport(""); }} /><button className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-400" onClick={clearFilters}>Clear filters</button></div></div>}
        </>}
      </header>
      {error && <p className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</p>}
      {tab === "marketplace" ? <section className="space-y-6"><p className="text-sm text-slate-400">{total.toLocaleString()} approved applications</p><div className="grid gap-4 md:grid-cols-2">{loading ? <p className="text-sm text-white/60">Loading...</p> : items.map((entry) => <MarketplaceCard key={entry.id} entry={entry} onDetails={() => setDetail(entry)} onConnect={() => void connect(entry)} />)}</div><Pagination page={page} hasNext={page < pages} onPrevious={() => setPage(page - 1)} onNext={() => setPage(page + 1)} /></section> : <section className="grid gap-4">{installed.map((server) => <InstalledCard key={server.id} server={server} onRefresh={async () => { await fetchWithAuth(`/mcp/servers/${server.id}/refresh`, { method: "POST" }); await load(); }} onInspect={() => window.location.assign(`/dashboard/mcp/inspector/${server.id}`)} onDisconnect={async () => { if (confirm("Disconnect this server?")) { await fetchWithAuth(`/mcp/servers/${server.id}`, { method: "DELETE" }); await load(); } }} />)}</section>}
      {detail && <DetailsModal entry={detail} onClose={() => setDetail(null)} onConnect={() => void connect(detail)} />}
    </main>
  );
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) { return <button className={`rounded-full border px-3 py-1.5 text-xs transition ${active ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-100" : "border-white/10 bg-white/5 text-white/65 hover:bg-white/10"}`} onClick={onClick}>{label}</button>; }

function MarketplaceCard({ entry, onDetails, onConnect }: { entry: MarketplaceEntry; onDetails: () => void; onConnect: () => void }) {
  const caps = capabilities(entry);
  const preview = entry.tool_preview || [];
  const connectable = entry.connectable ?? entry.trust_status === "approved";
  return <article className="flex h-full cursor-pointer flex-col rounded-2xl border border-white/10 bg-white/[0.04] p-4 shadow-lg shadow-black/10 transition hover:border-white/20 hover:bg-white/[0.07]" onClick={onDetails} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onDetails(); }} role="button" tabIndex={0}><div className="flex items-start justify-between gap-4"><div className="flex items-center gap-3"><div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-slate-900">{entry.logo_url ? <img alt={entry.name} className="h-full w-full object-cover" src={entry.logo_url} /> : <span className="text-sm font-semibold text-white/75">{entry.name.slice(0, 2).toUpperCase()}</span>}</div><div className="min-w-0"><h2 className="truncate text-base font-semibold">{entry.name}</h2><p className="text-xs text-white/55">{entry.publisher || "Official publisher"}</p></div></div><div className="text-right text-[10px] font-medium">{entry.official && <p className="text-emerald-300">OFFICIAL</p>}{entry.verified && <p className="text-sky-300">VERIFIED</p>}</div></div><p className="mt-3 min-h-12 text-sm leading-5 text-white/65">{entry.description || "Official MCP application with discoverable tools."}</p><div className="mt-3 flex flex-wrap gap-2 text-[11px] text-white/55"><span className="rounded-full border border-white/10 px-2.5 py-1">Remote</span><span className="rounded-full border border-white/10 px-2.5 py-1">{authLabel(entry)}</span><span className="rounded-full border border-white/10 px-2.5 py-1">{entry.tool_count == null ? (entry.catalog_status === "auth_required" ? "Connect to reveal tools" : "Catalog pending") : `${entry.tool_count} tools`}</span></div>{preview.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{preview.slice(0, 3).map((tool) => <span key={tool.name} className="rounded-full border border-white/10 bg-black/10 px-2.5 py-1 text-xs text-white/65">{tool.name}</span>)}</div>}{!connectable && entry.connectability_reason && <p className="mt-3 text-xs text-amber-200/80">{entry.connectability_reason}</p>}<div className="mt-4 flex items-center justify-between border-t border-white/5 pt-3 text-xs text-white/45"><span>{entry.source || "Official registry"}</span><span>{formatRelative(entry.last_seen_at)}</span></div><div className="mt-4 flex gap-2"><button className="rounded-lg border border-white/10 px-3 py-2 text-sm text-white/80 hover:bg-white/10" onClick={(event) => { event.stopPropagation(); onDetails(); }}>View details</button><button className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-sm font-medium text-sky-100 hover:bg-sky-400/15 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/5 disabled:text-white/35" disabled={!connectable} onClick={(event) => { event.stopPropagation(); onConnect(); }}>{connectable ? <><ExternalLink className="h-4 w-4" />Connect {entry.name}</> : entry.connectability_reason ? "Setup pending" : "Verification pending"}</button></div></article>;
}

function InstalledCard({ server, onRefresh, onInspect, onDisconnect }: { server: InstalledServer; onRefresh: () => Promise<void>; onInspect: () => void; onDisconnect: () => Promise<void> }) {
  const tone = statusTone(server.status);
  const config = server.config || {};
  const tools = Array.isArray(config.mcp_tools_cache) ? config.mcp_tools_cache.length : Number(config.mcp_catalog_tool_count || 0);
  const auth = config.oauth_mode === "none" ? "Anonymous" : "OAuth";
  return <article className="rounded-3xl border border-white/10 bg-white/5 p-5"><div className="flex items-start justify-between gap-4"><div><h2 className="text-lg font-semibold">{server.name}</h2><p className="mt-1 text-sm text-white/65">Remote · {auth} · {tools} tools</p>{typeof config.mcp_catalog_last_sync_at === "string" && <p className="mt-1 text-xs text-white/45">Last catalog sync: {formatRelative(config.mcp_catalog_last_sync_at)}</p>}{server.last_error && <p className="mt-3 text-sm text-red-300">{server.last_error}</p>}</div><span className={`rounded-full border px-3 py-1 text-xs font-semibold tracking-wide ${tone.className}`}>{tone.label}</span></div><div className="mt-4 flex flex-wrap gap-2"><button className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10" onClick={() => void onRefresh()}>Refresh catalog</button><button className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10" onClick={onInspect}>Inspect tools</button><button className="rounded-xl border border-red-400/20 px-4 py-2 text-sm text-red-200 hover:bg-red-400/10" onClick={() => void onDisconnect()}>Disconnect</button></div></article>;
}

function DetailsModal({ entry, onClose, onConnect }: { entry: MarketplaceEntry; onClose: () => void; onConnect: () => void }) {
  const caps = capabilities(entry);
  const preview = entry.tool_preview || [];
  const connectable = entry.connectable ?? entry.trust_status === "approved";
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}><div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-2xl border border-white/10 bg-[#202220] p-6 shadow-2xl" onClick={(event) => event.stopPropagation()}><div className="flex items-start justify-between gap-4"><div className="flex items-center gap-3"><div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-slate-900">{entry.logo_url ? <img alt={entry.name} className="h-full w-full object-cover" src={entry.logo_url} /> : <span className="font-semibold text-white/75">{entry.name.slice(0, 2).toUpperCase()}</span>}</div><div><div className="flex flex-wrap items-center gap-3"><h2 className="text-2xl font-semibold">{entry.name}</h2>{entry.official && <span className="text-sm text-emerald-300">OFFICIAL</span>}{entry.verified && <span className="text-sm text-sky-300">VERIFIED</span>}</div><p className="mt-1 text-sm text-white/55">{entry.publisher || "Official publisher"}</p></div></div><button aria-label="Close" className="rounded-full border border-white/10 p-2 text-white/70" onClick={onClose}><X className="h-4 w-4" /></button></div><p className="mt-5 text-sm leading-6 text-white/75">{entry.description || "Official MCP application with discoverable tools."}</p><div className="mt-6 grid gap-4 border-y border-white/10 py-5 md:grid-cols-2"><Info label="Publisher" value={entry.publisher || "Official publisher"} /><Info label="Transport" value="Remote MCP" /><Info label="Authentication" value={authLabel(entry)} /><Info label="Source" value={entry.source || "Official registry"} /><Info label="Last verified" value={formatDate(entry.last_seen_at)} /><Info label="MCP URL" value={entry.remote_url || "Vendor setup required"} /></div><section className="mt-6"><div className="flex items-center gap-2"><h3 className="text-sm font-semibold text-white/80">Tools</h3><span className="rounded-full bg-black/30 px-2 py-0.5 text-xs text-white/60">{entry.tool_count ?? preview.length}</span></div>{preview.length > 0 ? <ul className="mt-3 grid gap-2 md:grid-cols-2">{preview.map((tool) => <li key={tool.name} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2"><p className="text-sm text-white/85">{tool.name}</p>{tool.description && <p className="mt-1 text-xs leading-5 text-white/55">{tool.description}</p>}</li>)}</ul> : <p className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-white/60">{entry.catalog_status === "auth_required" ? "Connect to reveal this server's tools." : "Tool catalog is being discovered."}</p>}</section><div className="mt-6 grid gap-4 border-t border-white/10 pt-5 md:grid-cols-2"><Info label="Categories" value={(entry.categories || []).join(", ") || "General"} /><Info label="Catalog status" value={entry.catalog_status || "pending"} /></div>{entry.docs_url && <a className="mt-5 block text-sm text-sky-300 underline" href={entry.docs_url} rel="noreferrer" target="_blank">Open official setup documentation</a>}{!connectable && entry.connectability_reason && <p className="mt-5 rounded-lg border border-amber-400/20 bg-amber-400/10 p-3 text-sm text-amber-100">{entry.connectability_reason}</p>}<div className="mt-6 flex justify-end"><button className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-5 py-3 text-sm font-semibold text-sky-100 hover:bg-sky-400/15 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/5 disabled:text-white/35" disabled={!connectable} onClick={onConnect}>{connectable ? `Connect ${entry.name}` : entry.connectability_reason ? "Setup pending" : "Verification pending"}</button></div></div></div>;
}

function Info({ label, value }: { label: string; value: string }) { return <div><p className="text-xs uppercase tracking-wide text-white/40">{label}</p><p className="mt-1 break-all text-sm text-white/75">{value}</p></div>; }

function Pagination({ page, hasNext, onPrevious, onNext }: { page: number; hasNext: boolean; onPrevious: () => void; onNext: () => void }) { return <div className="flex items-center justify-center gap-4 text-sm text-slate-300"><button className="rounded px-2 py-1 disabled:opacity-40" disabled={page <= 1} onClick={onPrevious}>Previous</button><span>Page {page}</span><button className="rounded px-2 py-1 disabled:opacity-40" disabled={!hasNext} onClick={onNext}>Next</button></div>; }
