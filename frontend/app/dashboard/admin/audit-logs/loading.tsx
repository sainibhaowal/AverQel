"use client";

import Skeleton from "@/app/components/ui/Skeleton";

export default function LoadingAuditLogs() {
  return (
    <div className="flex min-h-[calc(100svh-160px)] flex-col space-y-8 pb-10 lg:h-[calc(100svh-160px)]">
      <div className="flex shrink-0 flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <Skeleton className="mb-2 h-10 w-48" />
          <Skeleton className="h-5 w-72" />
        </div>
        <div className="flex flex-wrap gap-4">
          <Skeleton className="h-12 w-[160px] rounded-xl" />
          <Skeleton className="h-12 w-[120px] rounded-xl" />
          <Skeleton className="h-12 w-12 rounded-xl" />
        </div>
      </div>

      <div className="glass-card border-glass-border flex min-h-0 flex-1 flex-col border">
        <div className="border-glass-border bg-muted/20 shrink-0 border-b p-4">
          <div className="flex items-center justify-between px-4">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-12" />
          </div>
        </div>

        <div className="divide-glass-border divide-y overflow-hidden p-2">
          {[1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="flex items-center justify-between p-4">
              <Skeleton className="h-6 w-32" />
              <div className="flex items-center gap-2">
                <Skeleton className="h-6 w-6 rounded-full" />
                <Skeleton className="h-6 w-24" />
              </div>
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-6 w-6" />
            </div>
          ))}
        </div>

        {/* Pagination Skeleton */}
        <div className="border-glass-border bg-muted/20 flex shrink-0 items-center justify-between border-t px-6 py-4">
          <Skeleton className="h-8 w-24 rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      </div>
    </div>
  );
}
