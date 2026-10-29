"use client";

import { useEffect } from "react";
import { AlertTriangle, Cable, RefreshCw } from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

export default function ProvidersErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Providers page error:", error);
  }, [error]);

  return (
    <div className="space-y-6">
      <DashboardSectionHeader
        title="Providers"
        subtitle="Runtime Control Plane"
        icon={Cable}
        accentClassName="bg-primary text-primary"
        accentGlowClassName="shadow-[0_0_18px_hsl(var(--primary)/0.28)]"
        backHref="/dashboard/settings"
        backLabel="Back"
      />

      <div className="settings-section p-6">
        <div className="border-warning/25 bg-warning/10 text-warning mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl border">
          <AlertTriangle size={20} />
        </div>
        <h2 className="text-foreground text-xl font-semibold tracking-tight">
          Providers failed to render
        </h2>
        <p className="text-foreground/80 mt-2 max-w-2xl text-sm leading-6">
          The providers control plane hit a client-side rendering error. Retry the route without
          refreshing the whole app first.
        </p>
        <button
          type="button"
          onClick={() => reset()}
          className="bg-primary text-primary-foreground shadow-primary/20 mt-5 inline-flex items-center gap-2 rounded-lg px-5 py-3 text-sm font-semibold shadow-lg transition-colors hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-primary/50 focus-visible:outline-none"
        >
          <RefreshCw size={14} />
          Retry Providers
        </button>
      </div>
    </div>
  );
}
