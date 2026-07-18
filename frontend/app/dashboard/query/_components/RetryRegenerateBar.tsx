"use client";

import { RefreshCcw } from "lucide-react";

interface RetryRegenerateBarProps {
  disabled?: boolean;
  onRegenerate: () => void;
}

export default function RetryRegenerateBar({
  disabled = false,
  onRegenerate,
}: RetryRegenerateBarProps) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        disabled={disabled}
        onClick={onRegenerate}
        className="border-glass-border/30 text-foreground/80 hover:border-primary/40 hover:text-primary inline-flex items-center gap-2 rounded-xl border bg-white/[0.03] px-3.5 py-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
      >
        <RefreshCcw size={14} />
        Regenerate
      </button>
    </div>
  );
}
