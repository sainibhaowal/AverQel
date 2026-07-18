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
        accentClassName="bg-cyan-400 text-cyan-300"
        accentGlowClassName="shadow-[0_0_18px_rgba(34,211,238,0.3)]"
        backHref="/dashboard/settings"
        backLabel="Back To Settings"
      />

      <div className="settings-section p-6">
        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-amber-400/20 bg-amber-400/10 text-amber-300">
          <AlertTriangle size={20} />
        </div>
        <h2 className="text-foreground text-xl font-semibold tracking-tight">
          Providers failed to render
        </h2>
        <p className="text-muted-foreground mt-2 max-w-2xl text-sm leading-6">
          The providers control plane hit a client-side rendering error. Retry the route without
          refreshing the whole app first.
        </p>
        <button
          type="button"
          onClick={() => reset()}
          className="mt-5 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-teal-500 to-cyan-500 px-5 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-900/20 transition-shadow hover:shadow-cyan-800/30"
        >
          <RefreshCw size={14} />
          Retry Providers
        </button>
      </div>
    </div>
  );
}
