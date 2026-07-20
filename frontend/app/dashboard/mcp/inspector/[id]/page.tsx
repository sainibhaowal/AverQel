"use client";

import { useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";

type InspectorData = {
  server: { name: string; status: string; transport: string; last_error?: string | null };
  diagnostics: {
    oauth_configured: boolean;
    credential_configured: boolean;
    reconnect_attempts: number;
    last_error?: string | null;
    last_catalog_sync_at?: string | null;
    active_tools: Array<{ name: string; description?: string; input_schema?: unknown }>;
  };
  events: Array<{ event_type: string; sequence: number; created_at: string }>;
};

export default function MCPInspector({ params }: { params: { id: string } }) {
  const [data, setData] = useState<InspectorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    const load = () => fetchWithAuth(`/mcp/servers/${params.id}/inspector`)
      .then(async (response) => { if (!response.ok) throw new Error("Inspector unavailable"); return response.json(); })
      .then((value) => { if (active) setData(value); })
      .catch((reason) => { if (active) setError(String(reason)); });
    void load();
    const timer = window.setInterval(load, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [params.id]);
  if (error) return <main className="p-6 text-red-400">{error}</main>;
  if (!data) return <main className="p-6">Loading inspector…</main>;
  const tone = data.server.status === "connected"
    ? "text-emerald-300 border-emerald-500/30 bg-emerald-500/10"
    : data.server.status === "failed"
      ? "text-red-300 border-red-500/30 bg-red-500/10"
      : "text-amber-300 border-amber-500/30 bg-amber-500/10";
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div><p className="text-sm text-slate-400">MCP Inspector</p><h1 className="text-2xl font-semibold">{data.server.name}</h1></div>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${tone}`}>{data.server.status}</span>
      </div>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Transport" value={data.server.transport} />
        <Metric label="Authentication" value={data.diagnostics.oauth_configured ? "OAuth configured" : data.diagnostics.credential_configured ? "Custom credentials" : "Not configured"} />
        <Metric label="Tools" value={String(data.diagnostics.active_tools.length)} />
        <Metric label="Reconnect attempts" value={String(data.diagnostics.reconnect_attempts)} />
      </section>
      {(data.server.last_error || data.diagnostics.last_error) && <p className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{data.server.last_error || data.diagnostics.last_error}</p>}
      <section className="rounded border border-white/10 p-4"><h2 className="mb-3 font-medium">Discovered tools</h2>{data.diagnostics.active_tools.length === 0 ? <p className="text-sm text-slate-400">No catalog tools discovered yet.</p> : <div className="grid gap-2 sm:grid-cols-2">{data.diagnostics.active_tools.map((tool) => <div key={tool.name} className="rounded bg-white/5 p-3"><p className="font-mono text-sm text-emerald-200">{tool.name}</p><p className="mt-1 text-xs text-slate-400">{tool.description || "No description provided."}</p></div>)}</div>}</section>
      <section className="rounded border border-white/10 p-4"><h2 className="mb-3 font-medium">Recent events</h2><div className="space-y-2">{data.events.length === 0 ? <p className="text-sm text-slate-400">No lifecycle events recorded.</p> : data.events.map((event) => <div key={`${event.sequence}-${event.event_type}`} className="flex flex-wrap justify-between gap-2 border-b border-white/5 py-2 text-sm"><span className="font-mono text-slate-200">{event.event_type}</span><span className="text-xs text-slate-500">#{event.sequence} {new Date(event.created_at).toLocaleString()}</span></div>)}</div></section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded border border-white/10 bg-white/[0.03] p-3"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-sm text-slate-100">{value}</p></div>;
}
