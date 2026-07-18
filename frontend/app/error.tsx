"use client";

import { useEffect } from "react";
import { AlertOctagon, RefreshCcw } from "lucide-react";
import AverQelLogo from "@/app/components/ui/AverQelLogo";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log the error to an error reporting service here if needed
    console.error("Global Error Boundary caught an error:", error);
  }, [error]);

  return (
    <div className="bg-background flex min-h-[100svh] w-full flex-col items-center justify-center p-6">
      <div className="absolute top-8 left-8">
        <AverQelLogo />
      </div>

      <div className="glass-card flex w-full max-w-md flex-col items-center p-8 text-center shadow-2xl">
        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10 text-red-500">
          <AlertOctagon size={32} />
        </div>

        <h1 className="text-foreground mb-2 text-2xl font-bold tracking-tight">System Error</h1>
        <p className="text-muted-foreground mb-6 max-w-sm text-sm">
          A critical rendering error occurred. The application state may be unstable.
          <br />
          <br />
          <span className="bg-muted line-clamp-3 rounded px-2 py-1 font-mono text-xs break-words text-red-400">
            {error.message || "Unknown rendering exception"}
          </span>
        </p>

        <button
          onClick={() => reset()}
          className="bg-primary hover:bg-primary/90 text-primary-foreground shadow-primary/20 flex items-center gap-2 rounded-full px-6 py-3 font-semibold shadow-lg transition-all"
        >
          <RefreshCcw size={16} />
          Recover Session
        </button>
      </div>
    </div>
  );
}
