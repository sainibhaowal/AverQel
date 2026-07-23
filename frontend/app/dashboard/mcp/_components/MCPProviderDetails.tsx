import Link from "next/link";
import { ArrowLeft, ExternalLink, Globe2 } from "lucide-react";

import { safeExternalUrl, type MCPConnection, type MCPMarketplaceEntry } from "@/lib/mcp-api";

import MCPCommunityWarning from "./MCPCommunityWarning";
import { MCPLogo } from "./MCPMarketplaceCard";
import MCPHealthStatus from "./MCPHealthStatus";

function transportLabel(value?: string | null): string {
  switch (value) {
    case "streamable_http": return "Remote HTTP";
    case "sse": return "Remote SSE";
    case "stdio": return "Local stdio";
    case "ssh": return "Remote SSH";
    default: return value ? value.replaceAll("_", " ") : "Remote";
  }
}

function riskLabel(value: string): string {
  return value === "external_message" ? "external message" : value;
}

function ExternalResource({ label, value }: { label: string; value?: string | null }) {
  const url = safeExternalUrl(value);
  if (!url) return null;
  return <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-sm text-sky-300 underline decoration-sky-300/30 underline-offset-4 hover:text-sky-200">{label}<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></a>;
}

export default function MCPProviderDetails({ entry, connectedServer, onConnect, onReconnect, connecting = false }: { entry: MCPMarketplaceEntry; connectedServer?: MCPConnection | null; onConnect: (entry: MCPMarketplaceEntry) => void; onReconnect?: (server: MCPConnection) => void; connecting?: boolean }) {
  const tools = entry.tools || entry.tool_preview || [];
  const badges = entry.badges || {};
  const isCommunity = entry.publisher_type === "community" || badges.community;
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-6 py-8">
      <Link href="/dashboard/mcp" className="inline-flex items-center gap-2 text-sm text-white/55 hover:text-white"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Back to marketplace</Link>
      <header className="flex flex-col gap-5 rounded-3xl border border-white/10 bg-white/[0.04] p-6 md:flex-row md:items-start md:justify-between">
        <div className="flex min-w-0 items-start gap-4"><MCPLogo entry={entry} size={64} /><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h1 className="text-2xl font-semibold text-white">{entry.name}</h1>{entry.official && !isCommunity && <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-2.5 py-1 text-xs text-emerald-200">Official</span>}{entry.verified && <span className="rounded-full border border-sky-400/25 bg-sky-400/10 px-2.5 py-1 text-xs text-sky-200">Verified</span>}</div><p className="mt-2 text-sm text-white/60">{entry.publisher || entry.author_name || "Publisher unavailable"}</p><div className="mt-3 flex flex-wrap gap-2 text-xs text-white/55"><span>{transportLabel(entry.transport)}</span><span>·</span><span>{entry.auth_type === "oauth" ? "OAuth" : entry.auth_type}</span>{entry.availability && <><span>·</span><span>{entry.availability}</span></>}</div></div></div>
        <button type="button" disabled={(!entry.connectable && !connectedServer) || connecting} onClick={() => connectedServer && onReconnect ? onReconnect(connectedServer) : onConnect(entry)} className="inline-flex shrink-0 items-center justify-center rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-900 hover:bg-slate-200 disabled:cursor-not-allowed disabled:bg-white/20 disabled:text-white/45">{connecting ? "Starting…" : connectedServer ? "Reconnect" : entry.connectable ? "Connect" : "Setup pending"}</button>
      </header>

      {isCommunity && <MCPCommunityWarning />}
      {!entry.connectable && entry.connectability_reason && <p className="rounded-xl border border-amber-400/25 bg-amber-400/10 p-4 text-sm text-amber-100">{entry.connectability_reason}</p>}

      <section className="grid gap-6 lg:grid-cols-[1.4fr_0.8fr]">
        <div className="space-y-6">
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="text-lg font-semibold text-white">About this connector</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-white/70">{entry.description || "No description is available."}</p><div className="mt-5 flex flex-wrap gap-x-5 gap-y-2"><ExternalResource label={entry.author_name ? `Author: ${entry.author_name}` : "Author website"} value={entry.author_website_url} /><ExternalResource label="Documentation" value={entry.docs_url} /><ExternalResource label="Support" value={entry.support_url} /><ExternalResource label="Privacy policy" value={entry.privacy_policy_url} /></div></section>
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><div className="flex items-center justify-between gap-4"><h2 className="text-lg font-semibold text-white">Reviewed tools</h2><span className="text-xs text-white/45">{entry.tool_count || tools.length} cataloged</span></div>{tools.length === 0 ? <p className="mt-4 text-sm text-white/50">This provider has no reviewed tools published yet.</p> : <div className="mt-4 divide-y divide-white/5">{tools.map((tool) => <div key={tool.name} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="font-mono text-sm text-emerald-200">{tool.name}</p><p className="mt-1 text-sm text-white/60">{tool.description || "No description provided."}</p></div><div className="flex shrink-0 flex-wrap gap-1.5">{(tool.risk_labels.length ? tool.risk_labels : ["read"]).map((risk) => <span key={risk} className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-white/60">{riskLabel(risk)}</span>)}{tool.category && <span className="rounded-full border border-white/10 px-2 py-1 text-[11px] text-white/45">{tool.category}</span>}</div></div>)}</div>}</section>
        </div>
        <aside className="space-y-6">
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="text-sm font-semibold uppercase tracking-wide text-white/55">Details</h2><dl className="mt-4 space-y-3 text-sm"><Detail label="Transport" value={transportLabel(entry.transport)} /><Detail label="Authentication" value={entry.auth_type === "oauth" ? "OAuth" : entry.auth_type} /><Detail label="Version" value={entry.version || "Catalog managed"} /><Detail label="Publisher" value={entry.publisher_type === "community" ? "Community" : "Official vendor"} /><Detail label="Supported products" value={entry.supported_products.join(", ") || "Not specified"} /><Detail label="Categories" value={[...entry.tool_categories, ...entry.categories].filter(Boolean).join(", ") || "Not specified"} /></dl><div className="mt-5 border-t border-white/5 pt-4"><p className="text-xs text-white/45">Connector URL</p><p className="mt-1 break-all font-mono text-xs text-white/70">{entry.remote_url || "Not published"}</p></div></section>
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="text-sm font-semibold uppercase tracking-wide text-white/55">Health and verification</h2><div className="mt-4"><MCPHealthStatus health={entry.health} /></div><dl className="mt-4 space-y-3 text-sm"><Detail label="Reviewed" value={formatDate(entry.reviewed_at)} /><Detail label="Next review" value={formatDate(entry.review_due_at)} /></dl></section>
          <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"><h2 className="text-sm font-semibold uppercase tracking-wide text-white/55">Requested OAuth scopes</h2>{entry.requested_scopes.length ? <ul className="mt-3 space-y-2 text-sm text-white/70">{entry.requested_scopes.map((scope) => <li key={scope} className="break-all rounded-lg bg-black/20 px-3 py-2 font-mono text-xs">{scope}</li>)}</ul> : <p className="mt-3 text-sm text-white/50">No OAuth scopes are listed.</p>}{entry.scope_note && <p className="mt-3 text-xs leading-5 text-white/45">{entry.scope_note}</p>}</section>
        </aside>
      </section>
      <p className="flex items-center gap-2 text-xs text-white/40"><Globe2 className="h-3.5 w-3.5" aria-hidden="true" />Endpoint health checks run on AverQel&apos;s backend; this page never probes vendor URLs from your browser.</p>
    </main>
  );
}

function Detail({ label, value }: { label: string; value: string }) { return <div className="flex items-start justify-between gap-4"><dt className="text-white/45">{label}</dt><dd className="text-right text-white/75">{value}</dd></div>; }
function formatDate(value?: string | null): string { if (!value) return "Not recorded"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "Unavailable" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date); }
