"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export interface MCPFilterOption {
  value: string;
  label: string;
}

interface MCPFilterSelectProps {
  label: string;
  value: string;
  options: MCPFilterOption[];
  onChange: (value: string) => void;
  className?: string;
}

export default function MCPFilterSelect({
  label,
  value,
  options,
  onChange,
  className = "",
}: MCPFilterSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative shrink-0 ${className}`}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className={`inline-flex h-10 min-w-[8.5rem] items-center justify-between gap-3 rounded-xl border px-3.5 text-left text-xs font-medium transition-colors ${
          open
            ? "border-cyan-300/35 bg-cyan-300/10 text-cyan-100 shadow-[0_0_18px_rgba(34,211,238,0.1)]"
            : "border-white/10 bg-[#0b100d]/90 text-slate-300 hover:border-white/20 hover:bg-white/[0.06]"
        }`}
      >
        <span className="truncate">{selected?.label || label}</span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-white/45 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute top-[calc(100%+0.5rem)] right-0 z-[80] min-w-full overflow-hidden rounded-2xl border border-white/15 bg-[#101713]/98 p-1.5 shadow-[0_18px_45px_rgba(0,0,0,0.5)] backdrop-blur-xl"
        >
          {options.map((option) => {
            const active = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={`flex w-full items-center justify-between gap-4 rounded-xl px-3 py-2 text-left text-xs transition-colors ${
                  active
                    ? "bg-cyan-300/15 text-cyan-100"
                    : "text-slate-300 hover:bg-white/[0.08] hover:text-white"
                }`}
              >
                <span className="whitespace-nowrap">{option.label}</span>
                {active ? <Check size={13} className="text-cyan-300" aria-hidden="true" /> : null}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
