"use client";

import { Activity, AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import type { ProviderHealth } from "@/lib/providers-api";

const STATUS_STYLES: Record<string, string> = {
  healthy: "border-green-500/30 bg-green-500/10 text-green-400",
  degraded: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  unhealthy: "border-red-500/30 bg-red-500/10 text-red-400",
};

export default function ProviderHealthBadge({ health }: { health: ProviderHealth | null }) {
  if (!health) {
    return (
      <span className="border-glass-border bg-muted text-muted-foreground inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-bold tracking-widest uppercase">
        <Clock size={12} />
        Unchecked
      </span>
    );
  }

  const status = health.status.toLowerCase();
  const className = STATUS_STYLES[status] || "border-glass-border bg-muted text-muted-foreground";
  const Icon =
    status === "healthy" ? CheckCircle2 : status === "unhealthy" ? AlertTriangle : Activity;

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-bold tracking-widest uppercase ${className}`}
    >
      <Icon size={12} />
      {status}
    </span>
  );
}
