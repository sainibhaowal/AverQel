"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import {
  connectMarketplaceEntry,
  getMarketplaceEntry,
  listMCPServers,
  startMCPServerOAuth,
  type MCPConnection,
  type MCPMarketplaceEntry,
} from "@/lib/mcp-api";

import MCPProviderDetails from "../../_components/MCPProviderDetails";

export default function MCPProviderPageClient() {
  const routeParams = useParams();
  const entryId =
    typeof routeParams?.entryId === "string"
      ? routeParams.entryId
      : Array.isArray(routeParams?.entryId)
        ? routeParams.entryId[0]
        : "";
  const [entry, setEntry] = useState<MCPMarketplaceEntry | null>(null);
  const [connectedServer, setConnectedServer] = useState<MCPConnection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    if (!entryId) return;
    let active = true;
    void Promise.all([getMarketplaceEntry(entryId), listMCPServers()])
      .then(([value, servers]) => {
        if (active) {
          setEntry(value);
          setConnectedServer(
            servers.find(
              (server) =>
                server.registry_entry_id === value.id ||
                (server.provider_slug && server.provider_slug === value.provider_slug),
            ) || null,
          );
        }
      })
      .catch((reason) => {
        if (active)
          setError(reason instanceof Error ? reason.message : "Provider details unavailable");
      });
    return () => {
      active = false;
    };
  }, [entryId]);

  const connect = async (value: MCPMarketplaceEntry) => {
    setConnecting(true);
    setError(null);
    try {
      const result = await connectMarketplaceEntry(value.id);
      if (result.authorization_url) window.location.assign(result.authorization_url);
      else
        window.location.assign(`/dashboard/mcp/inspector/${encodeURIComponent(result.server.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to connect provider.");
      setConnecting(false);
    }
  };

  const reconnect = async (server: MCPConnection) => {
    setConnecting(true);
    setError(null);
    try {
      const result = await startMCPServerOAuth(server.id);
      window.location.assign(result.authorization_url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reconnect provider.");
      setConnecting(false);
    }
  };

  if (error)
    return (
      <main className="mx-auto max-w-4xl p-6">
        <p
          className="rounded border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200"
          role="alert"
        >
          {error}
        </p>
      </main>
    );
  if (!entry)
    return (
      <main className="mx-auto max-w-4xl p-6 text-sm text-white/60">Loading provider details…</main>
    );
  return (
    <MCPProviderDetails
      entry={entry}
      connectedServer={connectedServer}
      onConnect={(value) => void connect(value)}
      onReconnect={(server) => void reconnect(server)}
      connecting={connecting}
    />
  );
}
