"use client";

import { Minus } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useId, useRef, useState } from "react";
import type { ProviderConfig } from "@/lib/providers-api";
import ProviderHealthBadge from "@/app/components/providers/ProviderHealthBadge";
import ProviderLogo from "@/app/components/providers/ProviderLogo";
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

      <div className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto pr-1">
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
                  <div className="flex h-10 items-center justify-between gap-3 pr-10">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center">
                      <ProviderLogo providerType={entry.provider_type} size={26} />
                    </div>
                    <div className="flex flex-row items-center gap-2">
                      <span
                        className={`rounded-lg border px-2 py-0.5 text-[8px] font-bold tracking-wider uppercase ${
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
                  <RemoveProviderButton
                    providerName={entry.display_name}
                    onRemove={() => onDelete(entry)}
                  />
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

interface RemoveProviderButtonProps {
  providerName: string;
  onRemove: () => void;
}

interface TooltipPosition {
  top: number;
  left: number;
  above: boolean;
}

function RemoveProviderButton({ providerName, onRemove }: RemoveProviderButtonProps) {
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState<TooltipPosition | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const tooltipId = useId();

  useEffect(() => {
    if (!tooltipOpen) return;

    const updatePosition = () => {
      const button = buttonRef.current;
      if (!button) return;

      const rect = button.getBoundingClientRect();
      const tooltipWidth = Math.min(160, window.innerWidth - 16);
      const halfWidth = tooltipWidth / 2;
      const left = Math.max(
        halfWidth + 8,
        Math.min(window.innerWidth - halfWidth - 8, rect.left + rect.width / 2),
      );
      const above = rect.top > 52;

      setTooltipPosition({
        top: above ? rect.top - 8 : rect.bottom + 8,
        left,
        above,
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [tooltipOpen]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          setTooltipOpen(false);
          onRemove();
        }}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") setTooltipOpen(true);
        }}
        onPointerLeave={() => setTooltipOpen(false)}
        onFocus={() => setTooltipOpen(true)}
        onBlur={() => setTooltipOpen(false)}
        aria-label={`Remove ${providerName}`}
        aria-describedby={tooltipOpen ? tooltipId : undefined}
        className="border-glass-border bg-surface-2 text-foreground/80 absolute top-5 right-3 z-20 flex h-8 w-8 items-center justify-center rounded-lg border transition-colors hover:border-red-500/45 hover:bg-red-500/12 hover:text-red-300 focus-visible:ring-2 focus-visible:ring-red-500/45 focus-visible:outline-none"
      >
        <Minus size={16} strokeWidth={2.5} aria-hidden="true" />
      </button>
      {tooltipOpen && tooltipPosition && typeof document !== "undefined"
        ? createPortal(
            <div
              id={tooltipId}
              role="tooltip"
              className="border-glass-border text-foreground pointer-events-none fixed z-[10000] w-max max-w-[calc(100vw-1rem)] rounded-lg border px-2.5 py-1.5 text-[11px] leading-tight font-semibold shadow-[0_12px_32px_rgba(0,0,0,0.45)]"
              style={{
                top: tooltipPosition.top,
                left: tooltipPosition.left,
                transform: `translate(-50%, ${tooltipPosition.above ? "-100%" : "0"})`,
                backgroundColor: "var(--background)",
              }}
            >
              Remove connection
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function CheckIcon() {
  return (
    <div className="bg-primary text-primary-foreground flex h-4 w-4 items-center justify-center rounded-lg">
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
