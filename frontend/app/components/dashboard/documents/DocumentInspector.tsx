"use client";

import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  AlertTriangle,
  Trash2,
  Shield,
  Loader2,
  Database,
  Eye,
  Zap,
  Cpu,
  Layers3,
  RefreshCcw,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import { readApiErrorMessage } from "@/app/lib/api/documents";

interface DocumentInspectorProps {
  isOpen: boolean;
  documentId: string | null;
  documentName: string;
  onClose: () => void;
  onDeleted: () => void;
}

interface InspectionData {
  document_id: string;
  status: string;
  processing_progress: number;
  active_stage: string;
  stage_progress: number;
  quarantined: boolean;
  information_yield: number | null;
  ingestion_status: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  last_error_code: string | null;
  last_error_message: string | null;
  extraction_method: string | null;
  extraction_coverage_score: number | null;
  extraction_ocr_used: boolean;
  extraction_vision_used: boolean;
  extraction_warnings: string[];
  embedding_provider: string | null;
  embedding_model: string | null;
  embedded_chunk_count: number;
}

export default function DocumentInspector({
  isOpen,
  documentId,
  documentName,
  onClose,
  onDeleted,
}: DocumentInspectorProps) {
  const [data, setData] = useState<InspectionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const statusRef = useRef<string | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isTerminalStatus = useCallback((status: string | null | undefined) => {
    return status ? ["indexed", "completed", "failed", "dead_lettered"].includes(status) : false;
  }, []);

  const loadInspection = useCallback(
    async (showSpinner: boolean) => {
      if (!documentId) return;
      if (showSpinner) {
        setLoading(true);
      }

      try {
        const res = (await fetchWithAuth(`/documents/${documentId}/status`)) as Response;
        if (!res.ok) {
          throw new Error(await readApiErrorMessage(res, "Failed to fetch status"));
        }
        const payload = (await res.json()) as InspectionData;
        setData(payload);
        statusRef.current = payload.status;
        setErrorMessage(null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to fetch status";
        console.error("Inspector fetch error", err);
        setErrorMessage(message);
      } finally {
        if (showSpinner) {
          setLoading(false);
        }
      }
    },
    [documentId],
  );

  useEffect(() => {
    if (!isOpen || !documentId) return;

    setShowDeleteConfirm(false);
    setErrorMessage(null);
    setData(null);
    statusRef.current = null;

    let intervalId: number | null = null;
    let cancelled = false;

    const start = async () => {
      await loadInspection(true);
      if (cancelled) return;

      intervalId = window.setInterval(() => {
        if (isTerminalStatus(statusRef.current)) {
          if (intervalId !== null) {
            window.clearInterval(intervalId);
          }
          return;
        }
        void loadInspection(false);
      }, 1500);
    };

    void start();

    return () => {
      cancelled = true;
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
    };
  }, [isOpen, documentId, loadInspection, isTerminalStatus]);

  const handleDelete = async () => {
    if (!documentId) return;
    setDeleting(true);
    setErrorMessage(null);
    try {
      const res = (await fetchWithAuth(`/documents/${documentId}`, {
        method: "DELETE",
      })) as Response;
      if (res.ok) {
        onDeleted();
        onClose();
        return;
      }
      setErrorMessage(await readApiErrorMessage(res, "Failed to delete document."));
    } catch (err) {
      console.error("Delete failed", err);
      setErrorMessage(err instanceof Error ? err.message : "Failed to delete document.");
    } finally {
      setDeleting(false);
    }
  };

  const yieldValue = data?.information_yield;
  const hasDataLoss = yieldValue !== null && yieldValue !== undefined && yieldValue < 100;
  const coverageScore = data?.extraction_coverage_score ?? 0;
  const progressValue = data?.processing_progress ?? 0;
  const embeddingProvider = data?.embedding_provider ?? "Pending";
  const embeddingModel = data?.embedding_model ?? "Pending";

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="border-glass-border dark:bg-surface-0 relative flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-[1.6rem] border bg-white shadow-2xl"
            onClick={(e: ReactMouseEvent<HTMLDivElement>) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="border-glass-border dark:bg-surface-1/50 flex shrink-0 items-center justify-between border-b bg-slate-50/50 p-8">
              <div className="flex items-center gap-4">
                <div className="bg-primary/10 border-primary/20 text-primary flex h-12 w-12 items-center justify-center rounded-2xl border shadow-[0_0_15px_rgba(var(--primary),0.1)]">
                  <Database size={24} className="stroke-[2.5]" />
                </div>
                <div className="overflow-hidden">
                  <h2 className="dark:text-foreground text-2xl font-black tracking-tight text-slate-900">
                    Metadata Inspector
                  </h2>
                  <div className="mt-0.5 flex items-center gap-2">
                    <div className="bg-primary/40 h-1.5 w-1.5 animate-pulse rounded-full" />
                    <p className="dark:text-foreground/80 max-w-[300px] truncate text-[10px] font-black tracking-widest text-slate-500 uppercase tabular-nums">
                      {documentName}
                    </p>
                  </div>
                </div>
              </div>
              <button
                onClick={onClose}
                className="bg-foreground/5 text-foreground/70 hover:text-accent hover:bg-accent/10 hover:border-accent/20 flex h-10 w-10 items-center justify-center rounded-xl border border-transparent transition-all"
              >
                <X size={20} className="stroke-[2.5]" />
              </button>
            </div>

            <div className="custom-scrollbar bg-muted/30 flex-1 space-y-8 overflow-y-auto p-8 dark:bg-transparent">
              {loading ? (
                <div className="flex flex-col items-center gap-4 py-24">
                  <Loader2 size={36} className="text-primary animate-spin" />
                  <p className="text-foreground/20 text-[10px] font-bold tracking-[0.3em] uppercase">
                    Decrypting Metadata Shards...
                  </p>
                </div>
              ) : data ? (
                <>
                  {/* Information Yield Meter */}
                  <div className="border-glass-border dark:bg-surface-1/80 rounded-[1.45rem] border bg-white p-6 shadow-[0_14px_36px_-28px_rgba(15,23,42,0.18)]">
                    <div className="mb-4 flex items-center justify-between">
                      <span className="text-foreground/80 flex items-center gap-2 text-[10px] font-black tracking-[0.3em] uppercase">
                        <Layers3 size={14} className="text-accent" /> Information Yield
                      </span>
                      <span
                        className={`text-xl font-black tabular-nums ${Number(yieldValue ?? 0) > 80 ? "text-emerald-500" : Number(yieldValue ?? 0) > 50 ? "text-accent" : "text-danger"}`}
                      >
                        {Math.round(Number(yieldValue ?? 0))}%
                      </span>
                    </div>
                    <div className="bg-foreground/5 relative h-2 w-full overflow-hidden rounded-full">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${yieldValue ?? 0}%` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                        className={`h-full rounded-full ${
                          Number(yieldValue ?? 0) > 80
                            ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]"
                            : Number(yieldValue ?? 0) > 50
                              ? "bg-accent shadow-[0_0_10px_rgba(251,191,36,0.3)]"
                              : "bg-danger"
                        }`}
                      />
                    </div>
                    {hasDataLoss && (
                      <div className="bg-warning/5 border-warning/10 mt-4 flex items-start gap-3 rounded-xl border p-4">
                        <AlertTriangle size={16} className="text-warning mt-0.5 shrink-0" />
                        <p className="text-warning text-[11px] leading-relaxed font-medium">
                          <strong className="text-warning uppercase">Partial Capture.</strong>{" "}
                          Approximately {Math.round(100 - Number(yieldValue ?? 0))}% of content was
                          discarded. This usually happens with non-selectable text or complex
                          diagrams.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Extraction Quality Grid */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="border-glass-border hover-yellow dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-5 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)] transition-all">
                      <p className="text-foreground/80 mb-1.5 flex items-center gap-2 text-[9px] font-black tracking-[0.3em] uppercase">
                        <Zap size={12} className="text-accent" /> Coverage
                      </p>
                      <p className="text-foreground text-2xl font-black tracking-tighter tabular-nums">
                        {Math.round(Number(coverageScore) * 100)}%
                      </p>
                    </div>
                    <div className="border-glass-border hover-yellow dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-5 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)] transition-all">
                      <p className="text-foreground/80 mb-1.5 flex items-center gap-2 text-[9px] font-black tracking-[0.3em] uppercase">
                        <Cpu size={12} className="text-primary" /> Pipeline
                      </p>
                      <p className="text-foreground truncate text-sm font-black tracking-tight">
                        {data.extraction_method || "standard_v1"}
                      </p>
                    </div>
                    <div className="border-glass-border hover-yellow dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-5 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)] transition-all">
                      <p className="text-foreground/50 mb-1.5 flex items-center gap-2 text-[9px] font-black tracking-[0.3em] uppercase">
                        <Eye size={12} /> OCR Status
                      </p>
                      <div className="flex items-center gap-2">
                        <span
                          className={`theme-pill !text-[9px] ${data.extraction_ocr_used ? "!bg-accent/10 !border-accent/30 !text-accent" : "!bg-foreground/5 !border-foreground/10 !text-foreground/20"}`}
                        >
                          {data.extraction_ocr_used ? "ACTIVE" : "INACTIVE"}
                        </span>
                      </div>
                    </div>
                    <div className="border-glass-border hover-yellow dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-5 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)] transition-all">
                      <p className="text-foreground/50 mb-1.5 flex items-center gap-2 text-[9px] font-black tracking-[0.3em] uppercase">
                        <Shield size={12} /> Vision AI
                      </p>
                      <div className="flex items-center gap-2">
                        <span
                          className={`theme-pill !text-[9px] ${data.extraction_vision_used ? "!bg-primary/10 !border-primary/30 !text-primary" : "!bg-foreground/5 !border-foreground/10 !text-foreground/20"}`}
                        >
                          {data.extraction_vision_used ? "ACTIVE" : "INACTIVE"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="border-glass-border dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-4 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)]">
                      <p className="text-foreground/50 mb-2 flex items-center gap-1.5 text-[9px] font-black tracking-[0.2em] uppercase">
                        <Cpu size={12} className="text-primary/60" /> Provider
                      </p>
                      <p className="text-foreground truncate text-[12px] font-bold">
                        {embeddingProvider}
                      </p>
                    </div>
                    <div className="border-glass-border dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-4 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)]">
                      <p className="text-foreground/50 mb-2 flex items-center gap-1.5 text-[9px] font-black tracking-[0.2em] uppercase">
                        <Layers3 size={12} className="text-primary/60" /> Embedding Model
                      </p>
                      <p className="text-foreground truncate text-[12px] font-bold">
                        {embeddingModel}
                      </p>
                    </div>
                    <div className="border-glass-border dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-4 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)]">
                      <p className="text-foreground/50 mb-2 flex items-center gap-1.5 text-[9px] font-black tracking-[0.2em] uppercase">
                        <Database size={12} className="text-primary/60" /> Vectors
                      </p>
                      <div className="flex items-center justify-between">
                        <p className="text-foreground text-[13px] font-black tabular-nums">
                          {data?.embedded_chunk_count || 0} Chunks
                        </p>
                        <Zap size={14} className="text-accent animate-pulse" />
                      </div>
                    </div>
                    <div className="border-glass-border dark:bg-surface-1/80 rounded-[1.35rem] border bg-white p-4 shadow-[0_12px_28px_-26px_rgba(15,23,42,0.14)]">
                      <p className="text-foreground/50 mb-2 flex items-center gap-1.5 text-[9px] font-black tracking-[0.2em] uppercase">
                        <RefreshCcw size={12} className="text-primary/60" /> Active Stage
                      </p>
                      <div className="flex items-center justify-between">
                        <p className="text-foreground text-[13px] font-black uppercase">
                          {data?.active_stage || data?.ingestion_status || data?.status || "queued"}
                        </p>
                        <span className="text-primary text-[12px] font-black tabular-nums">
                          {data?.stage_progress ?? 0}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Processing Status */}
                  <div className="group border-glass-border border-l-primary dark:bg-surface-1/80 rounded-[1.45rem] border border-l-4 bg-white p-6 shadow-[0_14px_36px_-28px_rgba(15,23,42,0.18)]">
                    <div className="mb-4 flex items-center justify-between">
                      <span className="text-foreground/60 flex items-center gap-2 text-[10px] font-black tracking-[0.3em] uppercase">
                        <RefreshCcw size={14} className="animate-spin-slow text-primary" /> Vector
                        Engine Status
                      </span>
                      <span
                        className={`theme-pill !text-[10px] ${
                          data.status === "indexed" || data.status === "completed"
                            ? "!border-emerald-500/20 !bg-emerald-500/10 !text-emerald-500"
                            : data.status === "failed" || data.status === "dead_lettered"
                              ? "!text-danger !bg-danger/10 !border-danger/20"
                              : "!text-primary !bg-primary/10 !border-primary/20 animate-pulse"
                        }`}
                      >
                        {data.status?.toUpperCase() || "PENDING"}
                      </span>
                    </div>
                    <div className="bg-foreground/5 relative h-2 w-full overflow-hidden rounded-full">
                      <div
                        className="bg-primary h-full rounded-full shadow-[0_0_10px_rgba(var(--primary),0.3)] transition-all duration-700"
                        style={{ width: `${progressValue}%` }}
                      />
                    </div>
                    <div className="text-foreground/80 mt-4 flex items-center justify-between text-[10px] font-black tracking-widest uppercase">
                      <span className="text-foreground/90 max-w-[200px] truncate font-black">
                        {data.active_stage ||
                          data.ingestion_status ||
                          "Awaiting Node Assignment..."}
                      </span>
                      <span className="text-primary text-sm font-black tabular-nums">
                        {progressValue}%
                      </span>
                    </div>

                    {data.last_error_message && (
                      <div className="bg-danger/5 border-danger/10 mt-4 rounded-xl border p-4">
                        <p className="text-danger/80 font-mono text-[10px] leading-relaxed font-bold">
                          <span className="mr-2 uppercase opacity-40">[FAIL_NODE_LOG]:</span>
                          {data.last_error_message}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Warnings */}
                  {data.extraction_warnings && data.extraction_warnings.length > 0 && (
                    <div className="border-warning/20 bg-warning/5 border-t-warning rounded-2xl border border-t-4 p-6">
                      <p className="text-warning/80 mb-4 flex items-center gap-2 text-[10px] font-black tracking-widest uppercase">
                        <AlertTriangle size={14} /> Extraction Anomalies Detected
                      </p>
                      <ul className="space-y-2.5">
                        {data.extraction_warnings.map((w, i) => (
                          <li
                            key={i}
                            className="text-warning/90 flex items-start gap-3 font-mono text-[11px] font-bold"
                          >
                            <div className="bg-warning/40 mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" />
                            {w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex flex-col items-center gap-4 py-24">
                  <AlertTriangle size={48} className="text-warning opacity-50" />
                  <p className="text-foreground/30 text-[11px] font-black tracking-[0.3em] uppercase">
                    {errorMessage || "Sync Protocol Error: Unable to access metadata shards."}
                  </p>
                </div>
              )}
            </div>

            {/* Footer Actions */}
            <div className="border-glass-border bg-surface-0 border-t p-8">
              {!showDeleteConfirm ? (
                <div className="flex gap-4">
                  <button
                    onClick={onClose}
                    className="dark:text-foreground/80 hover:text-primary hover:bg-primary/5 h-14 flex-1 rounded-2xl text-sm font-black tracking-[0.2em] text-slate-900 uppercase transition-all"
                  >
                    Dismiss
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    className="group dark:border-danger/10 dark:text-danger/60 dark:hover:bg-danger flex h-14 items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-8 text-xs font-black tracking-[0.2em] text-red-700 uppercase shadow-lg transition-all hover:border-red-600 hover:bg-red-600 hover:shadow-[0_0_18px_rgba(251,191,36,0.16),0_18px_36px_-20px_rgba(220,38,38,0.45)] dark:bg-transparent"
                  >
                    <Trash2
                      size={18}
                      className="stroke-[2.5] text-red-700 transition-colors group-hover:text-white dark:text-inherit"
                    />
                    <span className="text-red-700 transition-colors group-hover:text-white dark:text-inherit">
                      Purge Matrix
                    </span>
                  </button>
                </div>
              ) : (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-6"
                >
                  <div className="bg-danger/5 border-danger/20 flex items-center gap-4 rounded-2xl border p-5">
                    <div className="bg-danger/10 text-danger flex h-10 w-10 shrink-0 items-center justify-center rounded-full">
                      <AlertTriangle size={20} className="stroke-[2.5]" />
                    </div>
                    <p className="text-danger/80 text-[12px] leading-relaxed font-bold tracking-tight uppercase">
                      CRITICAL: Confirm Matrix Purge? This action is irreversible and will destroy
                      all associated vector shards.
                    </p>
                  </div>
                  <div className="flex gap-4">
                    <button
                      onClick={() => setShowDeleteConfirm(false)}
                      className="dark:text-foreground/80 hover:text-primary h-14 flex-1 rounded-2xl text-sm font-black tracking-[0.2em] text-slate-900 uppercase transition-all"
                    >
                      Abort Action
                    </button>
                    <button
                      onClick={handleDelete}
                      disabled={deleting}
                      className="bg-danger shadow-danger/20 flex h-14 flex-[2] items-center justify-center gap-3 rounded-2xl text-xs font-black tracking-[0.2em] text-white uppercase shadow-xl transition-all hover:brightness-110 disabled:opacity-50"
                    >
                      {deleting ? (
                        <>
                          <Loader2 size={18} className="animate-spin" /> Purging Shards...
                        </>
                      ) : (
                        <>
                          <Shield size={18} className="stroke-[2.5]" /> Confirm Destruction
                        </>
                      )}
                    </button>
                  </div>
                </motion.div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
