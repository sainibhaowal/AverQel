"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { PlugZap } from "lucide-react";

import {
  deleteMCPServer,
  listMCPServers,
  refreshMCPServer,
  type MCPConnection,
} from "@/lib/mcp-api";
import MCPHealthStatus from "./_components/MCPHealthStatus";
import MCPComposioPanel from "./_components/MCPComposioPanel";
import MCPLoadingIndicator from "./_components/MCPLoadingIndicator";
import { readMCPActiveContext } from "@/lib/mcp-context";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { useRealtimeEvents } from "@/lib/realtime";
import { averqelConfirm } from "@/app/components/ui/AverQelDialogHost";

export default function MCPDashboard() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [tab, setTab] = useState<"marketplace" | "installed">(() =>
    searchParams.get("tab") === "installed" ? "installed" : "marketplace",
  );
  const [installed, setInstalled] = useState<MCPConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [clientReady, setClientReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [callbackMessage, setCallbackMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setInstalled(await listMCPServers());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "MCP connections could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  useRealtimeEvents(() => {
    void load();
  }, ["mcp"]);

  useEffect(() => {
    queueMicrotask(() => setClientReady(true));
  }, []);

  useEffect(() => {
    const status = searchParams.get("mcp_status");
    const serverId = searchParams.get("server_id");
    if (!status) return;
    if (status === "connected" && serverId) {
      const context = readMCPActiveContext();
      const target = new URLSearchParams({ mcp_status: "connected" });
      if (context?.conversation_id) target.set("conversation_id", context.conversation_id);
      if (context?.deepspace_id) target.set("deepspace_id", context.deepspace_id);
      router.replace(
        `/dashboard/mcp/inspector/${encodeURIComponent(serverId)}?${target.toString()}`,
      );
      return;
    }
    queueMicrotask(() => {
      setTab("marketplace");
      setCallbackMessage("MCP authorization did not complete.");
    });
    const url = new URL(window.location.href);
    url.searchParams.delete("mcp_status");
    url.searchParams.delete("server_id");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }, [router, searchParams]);

  const connectedSlugs = installed
    .filter((server) => server.status === "connected")
    .map((server) => server.provider_slug || "")
    .filter(Boolean);
  const connectingSlugs = installed
    .filter((server) => server.status === "connecting")
    .map((server) => server.provider_slug || "")
    .filter(Boolean);

  return (
    <main className="mcp-theme-scope w-full min-w-0 space-y-8 pb-10">
      <header className="mcp-marketplace-header">
        <DashboardSectionHeader
          title="MCP Marketplace"
          subtitle="COMPOSIO CURATED APPS AND YOUR MCP CONNECTIONS"
          icon={PlugZap}
          accentClassName="bg-cyan-400 text-cyan-300"
          accentGlowClassName="shadow-[0_0_18px_rgba(34,211,238,0.35)]"
          actions={
            <div className="mcp-marketplace-actions flex flex-wrap gap-2">
              <button
                type="button"
                aria-current={tab === "marketplace" ? "page" : undefined}
                className={`rounded px-3 py-2 text-sm ${tab === "marketplace" ? "bg-white/15 text-white" : "border border-white/10 text-slate-300"}`}
                onClick={() => setTab("marketplace")}
              >
                Marketplace
              </button>
              <button
                type="button"
                aria-current={tab === "installed" ? "page" : undefined}
                className={`rounded px-3 py-2 text-sm ${tab === "installed" ? "bg-white/15 text-white" : "border border-white/10 text-slate-300"}`}
                onClick={() => setTab("installed")}
              >
                Installed ({installed.length})
              </button>
            </div>
          }
        />
      </header>
      {error && (
        <p
          className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200"
          role="alert"
        >
          {error}
        </p>
      )}
      {callbackMessage && (
        <p
          className="rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-100"
          role="status"
        >
          {callbackMessage}
        </p>
      )}
      {tab === "marketplace" ? (
        <MCPComposioPanel
          connectedProviderSlugs={connectedSlugs}
          connectingProviderSlugs={connectingSlugs}
          onConnected={() => {
            setTab("installed");
            void load();
          }}
        />
      ) : loading ? (
        <MCPLoadingIndicator
          label="Loading your MCP connections…"
          size="large"
          className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
        />
      ) : (
        <section className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
          {installed.length === 0 ? (
            <p className="rounded-2xl border border-white/10 p-6 text-sm text-white/55">
              No MCP connections yet. Browse Composio apps in Marketplace and connect one to
              DeepSpace.
            </p>
          ) : (
            installed.map((server) => (
              <InstalledCard
                key={server.id}
                server={server}
                clientReady={clientReady}
                onRefresh={async () => {
                  await refreshMCPServer(server.id);
                  await load();
                }}
                onDisconnect={async () => {
                  if (await averqelConfirm("Disconnect this MCP connection?")) {
                    await deleteMCPServer(server.id);
                    await load();
                  }
                }}
              />
            ))
          )}
        </section>
      )}
    </main>
  );
}

function InstalledCard({
  server,
  clientReady,
  onRefresh,
  onDisconnect,
}: {
  server: MCPConnection;
  clientReady: boolean;
  onRefresh: () => Promise<void>;
  onDisconnect: () => Promise<void>;
}) {
  const config = server.config || {};
  const statusTone =
    server.status === "connected"
      ? "text-emerald-300 border-emerald-500/30 bg-emerald-500/10"
      : server.status === "failed"
        ? "text-red-300 border-red-500/30 bg-red-500/10"
        : "text-amber-300 border-amber-500/30 bg-amber-500/10";
  return (
    <article className="mcp-installed-card rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">{server.name}</h2>
          <p className="mt-1 text-sm text-white/60">
            {transportLabel(server.transport)} ·{" "}
            {server.config?.oauth_mode === "none" ? "Anonymous" : "OAuth"} ·{" "}
            {Number(config.mcp_catalog_tool_count || 0)} tools
          </p>
          <p className="mt-1 text-xs text-white/45">
            Catalog revision {server.catalog_revision || 0}
            {clientReady && config.mcp_catalog_last_sync_at
              ? ` · Last refreshed ${formatRelative(config.mcp_catalog_last_sync_at)}`
              : ""}
          </p>
          {server.account_identity?.email && (
            <p className="mt-2 text-sm text-white/75">
              Connected account: {server.account_identity.email}
            </p>
          )}
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${statusTone}`}
        >
          {server.status}
        </span>
      </div>
      <div className="mt-4">
        <MCPHealthStatus
          health={{
            status: server.status === "connected" ? "healthy" : server.status,
            last_checked_at: config.mcp_catalog_last_sync_at,
          }}
          compact
        />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <a
          href={`/dashboard/mcp/inspector/${encodeURIComponent(server.id)}`}
          className="rounded-xl border border-white/10 px-4 py-2 text-sm text-white/80 hover:bg-white/10"
        >
          Manage connection
        </a>
        <button
          type="button"
          className="rounded-xl border border-white/10 px-4 py-2 text-sm text-white/80 hover:bg-white/10"
          onClick={() => void onRefresh()}
        >
          Refresh catalog
        </button>
        <button
          type="button"
          className="rounded-xl border border-red-400/20 px-4 py-2 text-sm text-red-200 hover:bg-red-400/10"
          onClick={() => void onDisconnect()}
        >
          Disconnect
        </button>
      </div>
    </article>
  );
}

function transportLabel(value?: string | null): string {
  switch (value) {
    case "streamable_http":
      return "Remote HTTP";
    case "sse":
      return "Remote SSE";
    case "stdio":
      return "Local stdio";
    case "ssh":
      return "Remote SSH";
    default:
      return value ? value.replaceAll("_", " ") : "Remote";
  }
}
function formatRelative(value?: string | null): string {
  if (!value) return "unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  const days = Math.round((date.getTime() - Date.now()) / 86400000);
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(days, "day");
}
