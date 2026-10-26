"use client";

import { Cable } from "lucide-react";
import ProviderLogo from "@/app/components/providers/ProviderLogo";
import RoundedSelect from "@/app/components/ui/RoundedSelect";
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
        <RoundedSelect
          id="p-type"
          label="Select Runtime Family"
          value={selectedType}
          onChange={onChange}
          options={[
            { value: "", label: "Choose a family..." },
            ...catalog.map((entry) => ({
              value: entry.provider_type,
              label: entry.display_name,
            })),
          ]}
          className="w-full"
          triggerClassName="w-full py-3.5 pr-10 pl-12 text-sm font-medium"
        />
        {selectedType ? (
          <div className="text-foreground/80 pointer-events-none absolute top-1/2 left-4 -translate-y-1/2">
            <ProviderLogo providerType={selectedType} size={18} />
          </div>
        ) : null}
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
              className={`rounded-lg px-3 py-1 text-[10px] font-semibold transition-all ${
                selected
                  ? "bg-cyan-400 text-slate-950 shadow-[0_0_12px_rgba(34,211,238,0.4)]"
                  : "text-foreground/40 hover:text-foreground/60 bg-white/5 hover:bg-white/10"
              }`}
            >
              <span className="flex items-center gap-1.5">
                <ProviderLogo providerType={entry.provider_type} size={14} />
                {entry.display_name}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
