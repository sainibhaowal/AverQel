"use client";

import { Minus, Zap, Cpu } from "lucide-react";
import type { ProviderConfig } from "@/lib/providers-api";
import ProviderHealthBadge from "@/app/components/providers/ProviderHealthBadge";
import { providerMatchesInventoryTab } from "@/app/components/providers/provider-visibility";

interface ProviderListTableProps {
  activeServiceKind: "chat" | "embedding" | "reranker" | "web" | "all";
  providers: ProviderConfig[];
  selectedProviderId: string | null;
  onSelect: (id: string) => void;
  onDelete?: (provider: ProviderConfig) => void;
  countLabel: string;
}

export default function ProviderListTable({
  activeServiceKind,
  providers,
  selectedProviderId,
  onSelect,
  onDelete,
}: ProviderListTableProps) {
  const filtered = providers.filter((p) => providerMatchesInventoryTab(p, activeServiceKind));

  return (
    <div className="flex h-full min-h-0 flex-col bg-transparent">
      <div className="border-glass-border mb-6 flex flex-col gap-1 border-b pb-6">
        <p className="text-muted-foreground font-mono text-[10px] tracking-[0.24em] uppercase">
          {activeServiceKind === "chat"
            ? "LLM Families"
            : activeServiceKind === "embedding"
              ? "Embedding Families"
              : activeServiceKind === "reranker"
                ? "Reranker Families"
                : "Web Search Families"}
        </p>
        <div className="flex items-center justify-between">
          <h2 className="text-foreground text-lg font-bold">Inventory</h2>
          <div className="theme-pill opacity-70">{filtered.length} options</div>
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        {filtered.length === 0 ? (
          <div className="text-muted-foreground border-glass-border rounded-2xl border border-dashed p-8 text-center text-xs italic">
            No active connections.
          </div>
        ) : (
          filtered.map((entry) => {
            const selected = entry.id === selectedProviderId;
            const isLocal = entry.is_local;

            return (
              <div
                key={entry.id}
                className={`group hover-yellow relative w-full rounded-[1.25rem] border transition-all duration-300 ${
                  selected
                    ? "border-primary/40 bg-surface-1 ring-primary/20 shadow-[0_4px_20px_-8px_hsl(var(--primary)/0.15)] ring-1"
                    : "border-glass-border bg-surface-0"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(entry.id)}
                  className="relative z-10 flex w-full flex-col space-y-3 rounded-[1.25rem] p-4 text-left"
                >
                  <div className="flex items-start justify-between gap-3 pr-10">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-colors ${
                        selected
                          ? "border-primary/30 bg-primary/10 text-primary"
                          : "border-glass-border bg-surface-2 text-muted-foreground"
                      }`}
                    >
                      {Boolean(entry.supports_chat) || Boolean(entry.supports_web_search) ? (
                        <Zap size={16} />
                      ) : (
                        <Cpu size={16} />
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1.5">
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[8px] font-bold tracking-wider uppercase ${
                          isLocal
                            ? "border-primary/20 bg-primary/5 text-primary"
                            : "border-glass-border bg-muted text-muted-foreground"
                        }`}
                      >
                        {isLocal ? "Managed" : "Hosted"}
                      </span>
                      {selected && <CheckIcon />}
                    </div>
                  </div>

                  <div className="min-w-0">
                    <div
                      className={`truncate text-sm font-bold tracking-tight ${selected ? "text-primary" : "text-foreground"}`}
                    >
                      {entry.display_name}
                    </div>
                    <div className="text-muted-foreground mt-0.5 truncate text-[11px] font-medium">
                      {entry.provider_type} · {entry.auth_mode.replace("_", " ")}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1 opacity-80">
                    <div className="flex items-center gap-1.5 grayscale-[0.5]">
                      <ProviderHealthBadge health={entry.latest_health || null} />
                    </div>
                  </div>
                </button>

                {onDelete ? (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(entry);
                    }}
                    aria-label={`Remove ${entry.display_name}`}
                    data-tooltip="Remove connection"
                    className="ui-tooltip ui-tooltip-top ui-tooltip-end border-glass-border bg-surface-1 text-muted-foreground absolute top-3 right-3 z-20 flex h-7 w-7 items-center justify-center rounded-full border transition-colors hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-300"
                  >
                    <Minus size={14} />
                  </button>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function CheckIcon() {
  return (
    <div className="bg-primary text-primary-foreground flex h-4 w-4 items-center justify-center rounded-full">
      <svg
        width="10"
        height="10"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    </div>
  );
}
