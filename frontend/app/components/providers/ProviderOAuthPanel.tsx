"use client";

import { ExternalLink, Link2Off, ShieldCheck } from "lucide-react";

import type { ProviderOAuthStatus } from "@/lib/providers-api";

interface ProviderOAuthPanelProps {
  status: ProviderOAuthStatus | null;
  connecting?: boolean;
  disconnecting?: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}

export default function ProviderOAuthPanel({
  status,
  connecting = false,
  disconnecting = false,
  onConnect,
  onDisconnect,
}: ProviderOAuthPanelProps) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-foreground/45 text-[11px] font-semibold tracking-[0.22em] uppercase">
          OpenAI / Codex Account Linking
        </p>
        <h3 className="text-foreground mt-2 text-xl font-semibold tracking-tight">
          Official account connection
        </h3>
        <p className="text-muted-foreground mt-1 text-sm">
          Use account linking only when the backend confirms the official provider flow is
          available.
        </p>
      </div>

      <div className="text-muted-foreground rounded-[1.5rem] border border-white/8 bg-white/[0.03] p-4 text-sm">
        {status ? status.message : "OAuth availability has not been checked yet."}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onConnect}
          disabled={!status?.available || connecting}
          className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(135deg,#14b8a6,#0ea5e9)] px-5 py-3 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ExternalLink size={14} />
          {status?.connected ? "Reconnect" : "Connect OpenAI / Codex"}
        </button>
        <button
          type="button"
          onClick={onDisconnect}
          disabled={!status?.connected || disconnecting}
          className="text-foreground/72 hover:text-foreground inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/15 px-5 py-3 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Link2Off size={14} />
          Disconnect
        </button>
      </div>

      <div className="text-foreground/55 inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/15 px-3 py-1 text-[11px] font-semibold tracking-[0.22em] uppercase">
        <ShieldCheck size={12} />
        {status?.connected ? "Connected via official provider flow" : "No linked OpenAI account"}
      </div>
    </div>
  );
}
