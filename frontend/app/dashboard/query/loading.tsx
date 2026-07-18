"use client";

import Skeleton from "@/app/components/ui/Skeleton";

export default function LoadingQuery() {
  return (
    <div className="flex min-h-[calc(100svh-160px)] flex-col gap-6 lg:h-[calc(100svh-160px)] lg:flex-row lg:gap-8">
      {/* Main Query Area */}
      <div className="flex-1 space-y-8 lg:pr-4">
        <div>
          <Skeleton className="mb-2 h-10 w-64" />
          <Skeleton className="h-5 w-80" />
        </div>

        {/* Input Area */}
        <div className="glass-card overflow-hidden">
          <div className="h-[140px] p-6">
            <Skeleton className="mb-3 h-6 w-3/4" />
            <Skeleton className="h-6 w-1/2" />
          </div>
          <div className="border-glass-border bg-muted/30 flex items-center justify-between border-t px-6 py-4">
            <div className="flex gap-6">
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-4 w-24" />
            </div>
            <Skeleton className="h-12 w-36 rounded-xl" />
          </div>
        </div>

        <div className="glass-card flex flex-col items-center p-12 text-center">
          <Skeleton className="mb-6 h-16 w-16 rounded-3xl" />
          <Skeleton className="mx-auto mb-4 h-8 w-48" />
          <Skeleton className="mx-auto h-4 w-64" />
        </div>
      </div>

      {/* Sidebar */}
      <div className="border-glass-border flex w-full flex-col gap-6 rounded-3xl border p-6 lg:w-80">
        <Skeleton className="mb-4 h-8 w-3/4" />

        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
          <Skeleton className="h-24 w-full rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
