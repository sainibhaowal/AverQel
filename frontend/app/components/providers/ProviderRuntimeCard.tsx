"use client";

import {
  Activity,
  AlertCircle,
  Bot,
  CheckCircle2,
  Database,
  Link2Off,
  RefreshCw,
  ScanSearch,
} from "lucide-react";

import ProviderHealthBadge from "@/app/components/providers/ProviderHealthBadge";
import ProviderLogo from "@/app/components/providers/ProviderLogo";
import type { ProviderConfig } from "@/lib/providers-api";

interface ProviderRuntimeCardProps {
  title: string;
  provider: ProviderConfig | null;
  pingState?: { status: string; message?: string; latency?: number };
  onPing: () => void;
  onDisconnect: () => void;
}

export default function ProviderRuntimeCard({
  title,
  provider,
  pingState,
  onPing,
  onDisconnect,
}: ProviderRuntimeCardProps) {
  return (
    <div className="providers-runtime-card theme-card flex h-fit flex-col gap-4 self-start">
      <div className="flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center">
          {provider ? (
            <ProviderLogo providerType={provider.provider_type} size={28} />
          ) : title.includes("LLM") ? (
            <Bot size={22} />
          ) : title.includes("Embedding") ? (
            <Database size={22} />
          ) : (
            <ScanSearch size={22} />
          )}
        </div>
        <ProviderHealthBadge health={provider?.latest_health || null} size="compact" />
      </div>

      <div className="space-y-1">
        <p className="text-foreground/75 font-mono text-[10px] font-bold tracking-[0.24em] uppercase">
          {title}
        </p>
        <h3 className="text-foreground truncate text-xl font-bold">
          {provider?.display_name ?? "None"}
        </h3>
        <p className="text-foreground/75 truncate text-sm font-medium">
          {provider?.default_chat_model ||
            provider?.default_embedding_model ||
            provider?.default_reranker_model ||
            "No model assigned"}
        </p>
      </div>

      <div className="border-glass-border border-t pt-4">
        {!pingState ? (
          provider ? (
            <p className="text-success text-xs font-bold tracking-widest uppercase">
              Ready by default
            </p>
          ) : (
            <p className="text-muted-foreground text-xs tracking-tighter uppercase">
              Connectivity status unknown
            </p>
          )
        ) : pingState.status === "pinging" ? (
          <div className="text-primary flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            <span className="text-[11px] font-bold tracking-widest uppercase">Pinging...</span>
          </div>
        ) : pingState.status === "healthy" ? (
          <div className="text-success flex items-center gap-2">
            <CheckCircle2 size={14} />
            <span className="truncate text-[11px] font-bold tracking-widest uppercase">
              {pingState.message}
            </span>
          </div>
        ) : (
          <div className="text-danger flex items-center gap-2">
            <AlertCircle size={14} />
            <span className="truncate text-[11px] font-bold tracking-widest uppercase">
              {pingState.message}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={onPing}
          className="theme-chip hover:text-primary flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[10px] font-bold tracking-widest uppercase transition-colors"
        >
          <Activity size={12} />
          Verify
        </button>
        <button
          onClick={onDisconnect}
          className="theme-chip hover:text-danger flex flex-1 items-center justify-center gap-2 rounded-xl py-2.5 text-[10px] font-bold tracking-widest uppercase transition-colors"
        >
          <Link2Off size={12} />
          Terminate
        </button>
      </div>
    </div>
  );
}
