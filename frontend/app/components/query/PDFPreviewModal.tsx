"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, ExternalLink, Maximize2, Minimize2, Loader2, FileText, Shield } from "lucide-react";
import { useEffect, useMemo, useState, type MouseEvent as ReactMouseEvent } from "react";

import { fetchWithAuth } from "@/lib/api";

interface PDFPreviewModalProps {
  isOpen: boolean;
  documentId: string | null;
  documentName: string;
  pageNumber?: number;
  onClose: () => void;
}

export default function PDFPreviewModal({
  isOpen,
  documentId,
  documentName,
  pageNumber,
  onClose,
}: PDFPreviewModalProps) {
  const [isMaximized, setIsMaximized] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const pdfUrl = useMemo(() => {
    if (!pdfBlobUrl) {
      return null;
    }
    return `${pdfBlobUrl}${pageNumber ? `#page=${pageNumber}` : ""}`;
  }, [pageNumber, pdfBlobUrl]);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;

    // Suppress extension errors while modal is open
    const originalError = console.error;
    const errorFilter = (...args: Parameters<typeof console.error>) => {
      const hasChromeExtensionMessage = args.some(
        (arg) => typeof arg === "string" && arg.includes("chrome-extension"),
      );
      if (hasChromeExtensionMessage) {
        return; // Silently ignore
      }
      originalError.apply(console, args);
    };

    if (isOpen) {
      console.error = errorFilter;
    }

    const loadPreview = async () => {
      setIsLoading(true);
      setLoadError(null);
      setPdfBlobUrl(null);

      if (!documentId || !isOpen) {
        setIsLoading(false);
        return;
      }

      const response = (await fetchWithAuth(`/documents/${documentId}/view`)) as Response;
      if (!response.ok) {
        let message = "Unable to load secure document preview.";
        try {
          const payload = (await response.json()) as {
            error?: { message?: string };
            detail?: string;
          };
          message = payload.error?.message || payload.detail || message;
        } catch {
          // Keep the generic message when the response is not JSON.
        }

        if (active) {
          setLoadError(message);
          setIsLoading(false);
        }
        return;
      }

      const blob = await response.blob();
      objectUrl = URL.createObjectURL(blob);
      if (!active) {
        URL.revokeObjectURL(objectUrl);
        return;
      }

      setPdfBlobUrl(objectUrl);
      setLoadError(null);
    };

    void loadPreview();

    return () => {
      active = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
      // Restore original console.error
      console.error = originalError;
    };
  }, [documentId, isOpen]);

  if (!isOpen || !documentId) return null;

  const handleOpenInNewTab = () => {
    if (!pdfUrl) {
      return;
    }
    window.open(pdfUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <AnimatePresence>
      <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-end">
        {/* Backdrop - only interactive part is the click-to-close */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="pointer-events-auto absolute inset-0 bg-slate-950/35 backdrop-blur-[2px] dark:bg-slate-950/40"
        />

        {/* Slide-out Sidebar/Modal */}
        <motion.div
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          className={`theme-panel-strong relative ${isMaximized ? "w-full" : "w-[650px]"} pointer-events-auto flex h-full flex-col border-l shadow-2xl`}
          onClick={(e: ReactMouseEvent<HTMLDivElement>) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="border-glass-border bg-foreground/[0.03] flex items-center justify-between border-b p-4 backdrop-blur-md dark:bg-slate-900/50">
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="bg-primary/10 text-primary flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
                <FileText size={16} />
              </div>
              <div className="min-w-0">
                <h3 className="text-foreground truncate text-sm font-bold">{documentName}</h3>
                {pageNumber && (
                  <p className="text-primary text-[10px] font-bold tracking-wider uppercase">
                    Cited on Page {pageNumber}
                  </p>
                )}
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => setIsMaximized(!isMaximized)}
                className="text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg p-2 transition-all"
                title={isMaximized ? "Minimize" : "Maximize"}
              >
                {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              </button>
              <button
                type="button"
                onClick={handleOpenInNewTab}
                disabled={!pdfUrl}
                className="text-muted-foreground hover:bg-muted hover:text-primary rounded-lg p-2 transition-all"
                title="Open in New Tab"
              >
                <ExternalLink size={16} />
              </button>
              <div className="bg-foreground/10 dark:bg-glass-border mx-1 h-4 w-px" />
              <button
                onClick={onClose}
                className="text-muted-foreground hover:bg-muted rounded-lg p-2 transition-all hover:text-red-400"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          {/* PDF Viewer Body */}
          <div className="bg-foreground/[0.03] relative flex-1 dark:bg-slate-800/50">
            {isLoading && (
              <div className="bg-background/95 absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 dark:bg-slate-900/80">
                <Loader2 size={32} className="text-primary animate-spin" />
                <p className="text-muted-foreground text-xs tracking-widest uppercase italic">
                  Loading secure document preview...
                </p>
              </div>
            )}

            {loadError ? (
              <div className="flex h-full items-center justify-center p-6">
                <div className="rounded-2xl border border-red-400/20 bg-red-500/8 px-4 py-3 text-sm text-red-100">
                  {loadError}
                </div>
              </div>
            ) : pdfUrl ? (
              <iframe
                src={pdfUrl}
                className="h-full w-full border-none"
                title="PDF Preview"
                onLoad={() => setIsLoading(false)}
              />
            ) : null}
          </div>

          {/* Footer Info */}
          <div className="border-glass-border bg-foreground/[0.03] flex items-center justify-between border-t p-3 dark:bg-slate-900/80">
            <div className="text-muted-foreground flex items-center gap-2 text-[10px] italic">
              <Shield size={12} className="text-primary/50" />
              <span>Strictly confidential • Enterprise analysis workspace</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="border-glass-border bg-muted text-muted-foreground rounded-full border px-2 py-0.5 font-mono text-[9px]">
                ID: {documentId.substring(0, 8)}
              </span>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
