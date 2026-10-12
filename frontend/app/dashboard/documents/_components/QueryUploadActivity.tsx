"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, LoaderCircle, Upload } from "lucide-react";
import { useSyncExternalStore } from "react";

import { getQueryUploadsSnapshot, subscribeQueryUploads } from "../../query/_lib/query-uploads";

export default function QueryUploadActivity({
  ownerId,
  documentIds,
  formatBytes,
}: {
  ownerId: string | null;
  documentIds: ReadonlySet<string>;
  formatBytes: (bytes: number) => string;
}) {
  const uploads = useSyncExternalStore(
    subscribeQueryUploads,
    getQueryUploadsSnapshot,
    getQueryUploadsSnapshot,
  );
  const visibleUploads = uploads.filter(
    (item) =>
      item.ownerId === ownerId &&
      item.status !== "ready" &&
      (!item.documentId || !documentIds.has(item.documentId)),
  );

  return (
    <AnimatePresence initial={false}>
      {visibleUploads.length > 0 ? (
        <motion.section
          aria-live="polite"
          aria-label="Grounded Query uploads"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="theme-panel overflow-hidden"
        >
          <div className="border-glass-border flex items-center gap-2 border-b px-4 py-3">
            <Upload size={15} className="text-primary" />
            <h2 className="text-foreground text-xs font-bold">Grounded Query uploads</h2>
            <span className="text-foreground/40 ml-auto text-[10px]">
              Live during app navigation
            </span>
          </div>
          <div className="divide-glass-border divide-y">
            {visibleUploads.map((item) => {
              const failed = item.status === "failed";
              const statusLabel =
                item.status === "queued"
                  ? "Waiting to upload"
                  : item.status === "uploading"
                    ? "Uploading to Documents Hub · security checks"
                    : failed
                      ? "Upload or indexing failed"
                      : "Indexing in Documents Hub";
              return (
                <div key={item.id} className="flex min-w-0 items-center gap-3 px-4 py-3">
                  <div
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border ${failed ? "border-danger/20 bg-danger/5 text-danger" : "border-primary/15 bg-primary/5 text-primary"}`}
                  >
                    {failed ? (
                      <AlertCircle size={17} />
                    ) : (
                      <LoaderCircle size={17} className="animate-spin" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground truncate text-xs font-semibold">{item.name}</p>
                    <p
                      className={`mt-1 text-[10px] ${failed ? "text-danger" : "text-foreground/50"}`}
                    >
                      {statusLabel}
                      {item.sizeBytes > 0 ? ` · ${formatBytes(item.sizeBytes)}` : ""}
                    </p>
                    {failed && item.error ? (
                      <p className="text-danger/80 mt-1 line-clamp-2 text-[10px]">{item.error}</p>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </motion.section>
      ) : null}
    </AnimatePresence>
  );
}
