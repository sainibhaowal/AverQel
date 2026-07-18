"use client";

import { Eye, EyeOff, KeyRound } from "lucide-react";
import { useState } from "react";

interface ProviderSecretFieldProps {
  value: string;
  onChange: (value: string) => void;
  maskedSummary?: string | null;
  disabled?: boolean;
  label?: string;
  className?: string;
}

export default function ProviderSecretField({
  value,
  onChange,
  maskedSummary,
  disabled = false,
  label = "API Key / Token",
  className,
}: ProviderSecretFieldProps) {
  const [showSecret, setShowSecret] = useState(false);

  return (
    <div className="space-y-2">
      <label className="text-muted-foreground block text-[10px] font-bold tracking-widest uppercase">
        {label}
      </label>
      <div className="relative">
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          type={showSecret ? "text" : "password"}
          placeholder={maskedSummary || "Enter secret value"}
          disabled={disabled}
          className={`border-glass-border bg-muted text-foreground w-full rounded-xl border px-4 py-3 pr-12 text-sm transition-colors outline-none focus:border-blue-500/50 disabled:opacity-60 ${className || ""}`}
        />
        <button
          type="button"
          onClick={() => setShowSecret((current) => !current)}
          className="text-muted-foreground hover:text-foreground absolute top-1/2 right-3 -translate-y-1/2"
          aria-label="Toggle secret visibility"
        >
          {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      <div className="text-muted-foreground flex items-center gap-2 text-xs">
        <KeyRound size={12} />
        <span>
          {maskedSummary
            ? `Saved secret: ${maskedSummary}`
            : "The backend stores only encrypted secret material."}
        </span>
      </div>
    </div>
  );
}
