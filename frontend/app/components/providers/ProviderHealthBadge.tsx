"use client";

import { Activity, AlertTriangle, CheckCircle2, Clock } from "lucide-react";
import type { ProviderHealth } from "@/lib/providers-api";

const STATUS_STYLES: Record<string, string> = {
  healthy: "border-green-500/30 bg-green-500/10 text-green-400",
  degraded: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  unhealthy: "border-red-500/30 bg-red-500/10 text-red-400",
};

const COMPACT_STATUS_STYLES: Record<string, string> = {
  healthy: "border-success/30 bg-success/10 text-success",
  degraded: "border-warning/30 bg-warning/10 text-warning",
  unhealthy: "border-danger/30 bg-danger/10 text-danger",
};

export default function ProviderHealthBadge({
  health,
  size = "default",
}: {
  health: ProviderHealth | null;
  size?: "default" | "compact";
}) {
  const compact = size === "compact";
  const sizeClasses = compact ? "gap-1.5 px-2 py-0.5 text-[10px]" : "gap-2 px-3 py-1 text-[11px]";
  const shapeClass = compact ? "rounded-lg" : "rounded-full";

  if (!health) {
    return (
      <span
        className={`border-glass-border bg-muted text-muted-foreground inline-flex items-center ${shapeClass} border font-bold tracking-widest uppercase ${sizeClasses}`}
      >
        <Clock size={12} />
        Unchecked
      </span>
    );
  }

  const status = health.status.toLowerCase();
  const styles = compact ? COMPACT_STATUS_STYLES : STATUS_STYLES;
  const className = styles[status] || "border-glass-border bg-muted text-muted-foreground";
  const Icon =
    status === "healthy" ? CheckCircle2 : status === "unhealthy" ? AlertTriangle : Activity;

  return (
    <span
      className={`inline-flex items-center ${shapeClass} border font-bold tracking-widest uppercase ${sizeClasses} ${className}`}
    >
      <Icon size={12} />
      {status}
    </span>
  );
}
