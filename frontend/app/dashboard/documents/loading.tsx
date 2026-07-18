"use client";

import Skeleton from "@/app/components/ui/Skeleton";

export default function LoadingDocuments() {
  return (
    <div className="space-y-8 pb-10">
      <div className="flex items-center justify-between">
        <div>
          <Skeleton className="mb-2 h-10 w-48" />
          <Skeleton className="h-5 w-72" />
        </div>
        <div className="flex gap-4">
          <Skeleton className="h-12 w-12 rounded-xl" />
          <Skeleton className="h-12 w-32 rounded-xl" />
        </div>
      </div>

      <div className="glass-card border-glass-border overflow-hidden border">
        <div className="border-glass-border bg-muted/20 border-b p-4">
          <div className="flex items-center justify-between px-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-12" />
          </div>
        </div>

        <div className="divide-glass-border divide-y">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center justify-between p-4">
              <div className="flex items-center gap-4">
                <Skeleton className="h-8 w-8 rounded-lg" />
                <Skeleton className="h-5 w-48" />
              </div>
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-8 w-8 rounded-lg" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
