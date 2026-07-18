"use client";

import { Cable } from "lucide-react";
import type { ProviderCatalogEntry } from "@/lib/providers-api";

interface ProviderTypeSelectorProps {
  catalog: ProviderCatalogEntry[];
  selectedType: string;
  onChange: (providerType: string) => void;
}

/**
 * Modern, compact provider family selector.
 * Replaces the old card-grid with a lightweight utility list.
 */
export default function ProviderTypeSelector({
  catalog,
  selectedType,
  onChange,
}: ProviderTypeSelectorProps) {
  return (
    <div className="flex flex-col space-y-2">
      <div className="flex items-center justify-between px-1">
        <label
          htmlFor="p-type"
          className="text-foreground/45 text-[10px] font-bold tracking-[0.2em] uppercase"
        >
          Select Runtime Family
        </label>
      </div>

      <div className="group relative">
        <select
          id="p-type"
          value={selectedType}
          onChange={(e) => onChange(e.target.value)}
          className="text-foreground w-full appearance-none rounded-xl border border-white/8 bg-white/[0.03] px-4 py-3.5 pr-10 text-sm font-medium transition-all outline-none hover:bg-white/[0.06] focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-500/10"
        >
          <option value="">Choose a family...</option>
          {catalog.map((entry) => (
            <option key={entry.provider_type} value={entry.provider_type}>
              {entry.display_name}
            </option>
          ))}
        </select>
        <div className="text-foreground/40 pointer-events-none absolute top-1/2 right-4 -translate-y-1/2">
          <Cable size={16} />
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 pt-1">
        {catalog.map((entry) => {
          const selected = entry.provider_type === selectedType;
          return (
            <button
              key={entry.provider_type}
              type="button"
              onClick={() => onChange(entry.provider_type)}
              className={`rounded-full px-3 py-1 text-[10px] font-semibold transition-all ${
                selected
                  ? "bg-cyan-400 text-slate-950 shadow-[0_0_12px_rgba(34,211,238,0.4)]"
                  : "text-foreground/40 hover:text-foreground/60 bg-white/5 hover:bg-white/10"
              }`}
            >
              {entry.display_name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
