"use client";

import { useParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  ArrowLeft,
  Database,
  Shield,
  ShieldCheck,
  Clock,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Maximize2,
  ChevronRight,
  Search,
  ChevronsDown,
  Sparkles,
  Download,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";
import { saveDocumentContentToDeepSpace } from "@/app/lib/deepspace-document-notes";
import toast from "react-hot-toast";
import Link from "next/link";

interface DocumentMetadata {
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256_hash: string;
  storage_bucket: string;
  storage_object_key: string;
  status: string;
  processing_progress: number;
  extraction_method: string | null;
  extraction_coverage_score: number | null;
  extraction_ocr_used: boolean;
  extraction_vision_used: boolean;
  extraction_warnings: string[];
  version: number;
  parent_document_id: string | null;
  created_at: string;
  updated_at: string;
}

interface VersionHistory {
  document_id: string;
  version: number;
  created_at: string;
  sha256_hash: string;
  status: string;
}

interface VersionsResponse {
  root_document_id: string;
  versions: VersionHistory[];
}

interface DocumentStatus {
  document_id: string;
  status: string;
  processing_progress: number;
  active_stage: string;
  stage_progress: number;
  ingestion_job_id: string | null;
  ingestion_status: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  last_error_code: string | null;
  last_error_message: string | null;
  dead_lettered_at: string | null;
  extraction_method: string | null;
  extraction_coverage_score: number | null;
  extraction_ocr_used: boolean;
  extraction_vision_used: boolean;
  extraction_warnings: string[];
  embedding_provider: string | null;
  embedding_model: string | null;
}

interface ChunkPreview {
  chunk_index: number;
  content: string;
  metadata?: Record<string, unknown>;
}

interface ChunksResponse {
  document_id: string;
  total_chunks: number;
  offset: number;
  limit: number;
  has_more: boolean;
  chunks: ChunkPreview[];
}

const CHUNK_PAGE_SIZE = 25;

function textToSafeNoteHtml(value: string): string {
  const escaped = value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
  return escaped
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${paragraph.replace(/\n/g, "<br/>")}</p>`)
    .join("");
}

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [doc, setDoc] = useState<DocumentMetadata | null>(null);
  const [status, setStatus] = useState<DocumentStatus | null>(null);
  const [versions, setVersions] = useState<VersionHistory[]>([]);
  const [chunks, setChunks] = useState<ChunkPreview[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [hasMoreChunks, setHasMoreChunks] = useState(false);
  const [loadingMoreChunks, setLoadingMoreChunks] = useState(false);
  const [loading, setLoading] = useState(true);
  const [fullTextLoading, setFullTextLoading] = useState(true);
  const [fullText, setFullText] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"reader" | "technical">("reader");
  const [selection, setSelection] = useState<{ text: string; x: number; y: number } | null>(null);
  const [downloading, setDownloading] = useState(false);

  const fetchChunks = useCallback(
    async (offset: number, append: boolean) => {
      if (!id) return;
      const response = (await fetchWithAuth(
        `/documents/${id}/chunks?limit=${CHUNK_PAGE_SIZE}&offset=${offset}`,
      )) as Response;
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as ChunksResponse;
      setTotalChunks(data.total_chunks);
      setHasMoreChunks(data.has_more);
      setChunks((current) => (append ? [...current, ...data.chunks] : data.chunks));
    },
    [id],
  );

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      const [metaRes, statusRes] = (await Promise.all([
        fetchWithAuth(`/documents/${id}`),
        fetchWithAuth(`/documents/${id}/status`),
      ])) as [Response, Response];

      if (metaRes.ok) setDoc(await metaRes.json());
      if (statusRes.ok) setStatus(await statusRes.json());
      await fetchChunks(0, false);

      try {
        const versionsRes = (await fetchWithAuth(`/documents/${id}/versions`)) as Response;
        if (versionsRes.ok) {
          const data = (await versionsRes.json()) as VersionsResponse;
          setVersions(data.versions);
        }
      } catch (e) {
        console.error("Failed to fetch versions", e);
      }

      // The document shell and fragments are useful immediately. Full text
      // can be large, so it must not block the first render of the page.
      setLoading(false);

      try {
        const fullRes = (await fetchWithAuth(`/documents/${id}/full-text`)) as Response;
        if (fullRes.ok) {
          const data = await fullRes.json();
          setFullText(data.content);
        }
      } catch (e) {
        console.error("Failed to fetch full text", e);
      } finally {
        setFullTextLoading(false);
      }
    } catch (error) {
      console.error("Failed to fetch document details", error);
    } finally {
      setLoading(false);
    }
  }, [fetchChunks, id]);

  const handleLoadMoreChunks = useCallback(async () => {
    if (loadingMoreChunks || !hasMoreChunks) {
      return;
    }
    setLoadingMoreChunks(true);
    try {
      await fetchChunks(chunks.length, true);
    } finally {
      setLoadingMoreChunks(false);
    }
  }, [chunks.length, fetchChunks, hasMoreChunks, loadingMoreChunks]);

  const handleSendToNote = async (content: string) => {
    try {
      await saveDocumentContentToDeepSpace({
        title: `Extract: ${doc?.filename.slice(0, 40) || "Document"}`,
        contentHtml: textToSafeNoteHtml(content),
      });
      toast.success("Content added to your active DeepSpace note.");
    } catch (err) {
      console.error("Send to note failed", err);
      toast.error(err instanceof Error ? err.message : "Failed to send to notes.");
    }
  };

  const handleDownload = async () => {
    if (!doc || downloading) return;
    setDownloading(true);
    try {
      const response = (await fetchWithAuth(`/documents/${doc.document_id}/download`)) as Response;
      if (!response.ok) throw new Error("Unable to download the original file.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = doc.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Document download failed", error);
      alert(error instanceof Error ? error.message : "Unable to download the original file.");
    } finally {
      setDownloading(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    queueMicrotask(() => void fetchData());

    // Auto-poll status if not terminal
    const interval = setInterval(async () => {
      try {
        const res = (await fetchWithAuth(`/documents/${id}/status`)) as Response;
        if (res.ok) {
          const data = await res.json();
          setStatus(data);

          // Refresh metadata too if status changed to terminal
          if (["completed", "failed", "dead_lettered", "indexed"].includes(data.status)) {
            const metaRes = (await fetchWithAuth(`/documents/${id}`)) as Response;
            if (metaRes.ok) setDoc(await metaRes.json());
          }

          if (["completed", "failed", "dead_lettered", "indexed"].includes(data.status)) {
            clearInterval(interval);
          }
        }
      } catch (error) {
        console.error("Polling error", error);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [fetchData, id]);

  if (loading) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-4">
        <Loader2 size={48} className="text-primary animate-spin" />
        <p className="font-medium text-slate-500 italic">Resolving knowledge node...</p>
      </div>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-4">
        <AlertCircle size={48} className="text-red-500" />
        <p className="text-foreground text-xl font-bold">Document Not Found</p>
        <Link href="/dashboard/documents" prefetch={false} className="text-primary hover:underline">
          Return to list
        </Link>
      </div>
    );
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const steps = [
    { id: "security", label: "Security scan", icon: <ShieldCheck size={18} /> },
    { id: "queued", label: "Queued", icon: <Clock size={18} /> },
    { id: "downloading", label: "Downloading", icon: <Download size={18} /> },
    { id: "parsing", label: "Parsing", icon: <Maximize2 size={18} /> },
    { id: "chunking", label: "Chunking", icon: <Database size={18} /> },
    { id: "embedding", label: "Embedding", icon: <Sparkles size={18} /> },
    { id: "indexed", label: "Indexed", icon: <CheckCircle2 size={18} /> },
  ];

  const activePipelineStatus =
    status?.active_stage || status?.ingestion_status || status?.status || doc.status;
  const normalizedStatus = activePipelineStatus === "completed" ? "indexed" : activePipelineStatus;
  const currentStepIdx = steps.findIndex((s) => s.id === normalizedStatus);
  // Documents are created only after the upload security gate passes. Keep
  // that gate visible as a completed first step without inventing a worker
  // status that the ingestion API does not expose.
  const boundedStepIndex = currentStepIdx >= 0 ? currentStepIdx : 1;
  const isFailed =
    (status?.status || doc.status) === "failed" ||
    (status?.status || doc.status) === "dead_lettered";
  const overallProgress = status?.processing_progress ?? doc.processing_progress ?? 0;

  const cleanText = (text: string) => {
    // Merge lines that don't end in a period or other terminal punctuation
    return text
      .split("\n")
      .map((line) => line.trim())
      .join(" ")
      .replace(/\s+/g, " ")
      .replace(/([.?!])\s+/g, "$1\n\n");
  };

  const handleTextSelection = (e: React.MouseEvent) => {
    const sel = window.getSelection();
    const text = sel?.toString().trim();
    if (text && text.length > 5) {
      setSelection({
        text,
        x: e.clientX,
        y: e.clientY - 40,
      });
    } else {
      setSelection(null);
    }
  };

  return (
    <div className="space-y-8 pb-12">
      <Link
        href="/dashboard/documents"
        prefetch={false}
        className="hover:text-foreground group mb-4 inline-flex items-center gap-2 text-slate-700 transition-colors dark:text-slate-400"
      >
        <ArrowLeft size={18} className="transition-transform group-hover:-translate-x-1" />
        <span className="text-sm font-semibold">Back to Documents</span>
      </Link>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card flex items-start gap-6 p-8"
          >
            <div className="bg-primary/10 text-primary flex h-16 w-16 items-center justify-center rounded-2xl">
              <FileText size={32} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex items-center justify-between gap-4">
                <h1 className="text-foreground truncate text-3xl font-bold">{doc.filename}</h1>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={handleDownload}
                    disabled={downloading}
                    className="border-primary/20 bg-primary/5 text-primary hover:bg-primary/10 flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-bold transition disabled:opacity-60"
                  >
                    <Download size={16} className={downloading ? "animate-bounce" : ""} />
                    <span>{downloading ? "Downloading" : "Download"}</span>
                  </button>
                  <Link
                    href={`/dashboard/query?docId=${doc.document_id}`}
                    prefetch={false}
                    className="bg-primary text-primary-foreground flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-bold shadow-[0_12px_24px_rgba(var(--primary),0.2)] transition-all hover:shadow-[0_12px_32px_rgba(var(--primary),0.35)]"
                  >
                    <Search size={16} />
                    <span>Ask Questions</span>
                  </Link>
                </div>
              </div>
              <div className="flex gap-4 text-sm font-medium text-slate-700 dark:text-slate-400">
                <span className="flex items-center gap-1.5">
                  <Clock size={14} /> {new Date(doc.created_at).toLocaleString()}
                </span>
                <span className="flex items-center gap-1.5 text-[10px] font-bold tracking-wider uppercase">
                  <Database size={14} /> {doc.content_type.split("/")[1]}
                </span>
                <span className="flex items-center gap-1.5">
                  <Shield size={14} /> {formatBytes(doc.size_bytes)}
                </span>
              </div>
            </div>
          </motion.div>

          <div className="space-y-6">
            <h2 className="text-foreground text-xl font-bold">Ingestion Pipeline</h2>
            <div className="glass-card p-10">
              <div className="relative flex justify-between">
                {/* Background Track */}
                <div className="absolute top-[21px] left-0 z-0 h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-800/80" />

                {/* Active Progress Track */}
                <div
                  className="absolute top-[21px] left-0 z-0 h-1.5 rounded-full bg-gradient-to-r from-teal-500 to-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.45)] transition-all duration-1000"
                  style={{
                    width: `${Math.max(0, (boundedStepIndex / (steps.length - 1)) * 100)}%`,
                  }}
                />

                {steps.map((step, idx) => {
                  const isCompleted = idx < boundedStepIndex || normalizedStatus === "indexed";
                  const isActive =
                    idx === boundedStepIndex && normalizedStatus !== "indexed" && !isFailed;

                  return (
                    <div key={step.id} className="group relative z-10 flex flex-col items-center">
                      <div className="relative">
                        {/* Pulse Ring for Active Node */}
                        {isActive && (
                          <div className="pointer-events-none absolute inset-[-4px] animate-[ping_1.8s_ease-in-out_infinite] rounded-xl border border-emerald-400/50" />
                        )}
                        <div
                          className={`relative z-10 flex h-11 w-11 items-center justify-center rounded-xl border transition-all duration-500 ${
                            isCompleted
                              ? "border-none bg-gradient-to-br from-teal-500 to-emerald-600 text-white shadow-[0_4px_14px_rgba(13,148,136,0.3)]"
                              : isActive
                                ? "scale-110 border-2 border-emerald-600 bg-white text-emerald-700 shadow-[0_0_24px_rgba(16,185,129,0.35)] dark:border-emerald-500 dark:bg-[#101512] dark:text-emerald-400 dark:shadow-[0_0_20px_rgba(16,185,129,0.45)]"
                                : "border-slate-300 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-900/30 dark:text-slate-600"
                          } `}
                        >
                          {isCompleted ? (
                            <CheckCircle2 size={16} className="stroke-[2.5]" />
                          ) : (
                            step.icon
                          )}
                        </div>
                      </div>
                      <span
                        className={`mt-4 text-[10px] tracking-[0.16em] uppercase transition-colors ${
                          isCompleted
                            ? "font-bold text-slate-800 dark:text-slate-200"
                            : isActive
                              ? "font-extrabold text-emerald-700 dark:text-emerald-400"
                              : "font-medium text-slate-500 dark:text-slate-600"
                        }`}
                      >
                        {step.label}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Progress Console */}
              <div className="mt-12 space-y-4 rounded-2xl border border-slate-200 bg-slate-50/70 p-6 dark:border-slate-800/80 dark:bg-black/10">
                <div className="flex items-center justify-between text-[11px] font-bold tracking-[0.2em] uppercase">
                  <div className="flex items-center gap-2">
                    {!isFailed && normalizedStatus !== "indexed" && (
                      <span className="h-2 w-2 animate-ping rounded-full bg-emerald-500" />
                    )}
                    <span className="text-slate-500">Current Phase:</span>
                    <span
                      className={`font-black ${isFailed ? "text-red-600" : "text-emerald-750 dark:text-emerald-400"}`}
                    >
                      {isFailed ? "FAILED" : activePipelineStatus.replace("_", " ")}
                    </span>
                  </div>
                  <span className="font-black text-teal-800 tabular-nums dark:text-teal-300">
                    {overallProgress}%
                  </span>
                </div>
                <div className="relative h-3 overflow-hidden rounded-full bg-slate-200/60 p-[2px] shadow-inner dark:bg-slate-800/80">
                  <div
                    className="relative h-full overflow-hidden rounded-full bg-gradient-to-r from-teal-500 via-emerald-400 to-emerald-500 transition-all duration-700"
                    style={{
                      width: `${overallProgress}%`,
                      boxShadow: "0 0 10px rgba(16, 185, 129, 0.3)",
                    }}
                  >
                    {/* Shimmer overlay */}
                    {!isFailed && overallProgress < 100 && <div className="progress-bar-shimmer" />}
                  </div>
                </div>
              </div>

              {isFailed && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="mt-12 flex items-start gap-4 rounded-2xl border border-red-500/10 bg-red-500/5 p-6"
                >
                  <AlertCircle className="shrink-0 text-red-500" size={24} />
                  <div>
                    <p className="mb-1 font-bold text-red-500">Ingest Failure</p>
                    <p className="text-sm text-red-500/70">
                      {status?.last_error_message ||
                        "An unexpected error occurred during processing."}
                    </p>
                    {status?.attempt_count && (
                      <p className="mt-2 text-[10px] font-bold text-red-500/40 uppercase">
                        Failed after {status.attempt_count} attempts
                      </p>
                    )}
                  </div>
                </motion.div>
              )}
            </div>
          </div>

          <div className="space-y-6">
            <h2 className="text-foreground flex items-center gap-2 text-xl font-bold">
              <Database size={20} className="text-primary" />
              Content Preview
            </h2>
            <div className="glass-card overflow-hidden">
              <div className="bg-foreground/[0.04] border-glass-border/60 flex items-center justify-between border-b px-8 py-3 dark:bg-white/5">
                <div className="flex gap-6">
                  <button
                    onClick={() => setViewMode("reader")}
                    className={`pb-1 text-[10px] font-black tracking-widest uppercase transition-all ${
                      viewMode === "reader"
                        ? "text-primary border-primary border-b-2"
                        : "text-foreground/40 hover:text-foreground"
                    }`}
                  >
                    Reader Mode
                  </button>
                  <button
                    onClick={() => setViewMode("technical")}
                    className={`pb-1 text-[10px] font-black tracking-widest uppercase transition-all ${
                      viewMode === "technical"
                        ? "text-primary border-primary border-b-2"
                        : "text-foreground/40 hover:text-foreground"
                    }`}
                  >
                    Technical Fragments
                  </button>
                </div>
                <div className="text-foreground/30 text-[10px] font-bold tracking-wider uppercase">
                  {viewMode === "reader"
                    ? fullText?.length
                      ? `${Math.ceil(fullText.length / 5)} words`
                      : "Reading..."
                    : `${chunks.length} fragments`}
                </div>
              </div>
              <div
                className="custom-scrollbar relative max-h-[600px] overflow-y-auto p-12"
                onMouseUp={handleTextSelection}
              >
                {viewMode === "reader" ? (
                  fullText ? (
                    <div className="prose prose-lg prose-slate dark:prose-invert max-w-none">
                      <div className="text-foreground/90 selection:bg-primary/30 selection:text-primary-foreground font-serif text-[19px] leading-[1.8] tracking-tight whitespace-pre-wrap">
                        {cleanText(fullText)}
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-4 py-24">
                      {fullTextLoading ? (
                        <Loader2 size={32} className="text-primary/20 animate-spin" />
                      ) : (
                        <AlertCircle size={32} className="text-foreground/20" />
                      )}
                      <p className="text-foreground/30 text-[10px] font-bold tracking-widest uppercase">
                        {fullTextLoading
                          ? "Loading document text without blocking the page"
                          : "No extracted text available"}
                      </p>
                    </div>
                  )
                ) : (
                  <div className="space-y-6">
                    {chunks.length > 0 ? (
                      chunks.map((chunk) => (
                        <div
                          key={chunk.chunk_index}
                          className="border-primary/30 relative border-l pl-6"
                        >
                          <div className="bg-primary absolute top-0 left-[-5px] h-2.5 w-2.5 rounded-full shadow-[0_0_8px_rgba(var(--primary),0.5)]" />
                          <div className="mb-3 flex items-center justify-between">
                            <p className="text-primary text-[10px] font-bold tracking-[0.2em] uppercase">
                              Fragment {chunk.chunk_index + 1}
                            </p>
                            <button
                              onClick={() => handleSendToNote(chunk.content)}
                              className="bg-primary/10 text-primary hover:bg-primary flex items-center gap-2 rounded-lg px-3 py-1 text-[9px] font-bold tracking-widest uppercase transition-all hover:text-white"
                            >
                              <Sparkles size={12} />
                              Send to Note
                            </button>
                          </div>
                          <p className="text-foreground/82 font-mono text-sm leading-relaxed whitespace-pre-wrap">
                            {chunk.content}
                          </p>
                        </div>
                      ))
                    ) : (
                      <div className="py-12 text-center">
                        <p className="text-sm text-slate-500 italic">No fragments available.</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Floating Selection Bubble */}
                <AnimatePresence>
                  {selection && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.9, y: 10 }}
                      animate={{ opacity: 1, scale: 1, y: 0 }}
                      exit={{ opacity: 0, scale: 0.9, y: 10 }}
                      style={{
                        position: "fixed",
                        left: selection.x,
                        top: selection.y,
                        transform: "translateX(-50%)",
                      }}
                      className="z-[100]"
                    >
                      <button
                        onClick={() => {
                          handleSendToNote(selection.text);
                          setSelection(null);
                        }}
                        className="bg-primary text-primary-foreground flex items-center gap-2 rounded-full px-4 py-2 text-xs font-black tracking-widest uppercase shadow-2xl transition-all hover:scale-105 active:scale-95"
                      >
                        <Sparkles size={14} />
                        Add to Note
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
              <div className="border-glass-border/60 bg-primary/5 flex flex-col items-center gap-3 border-t p-4">
                <p className="text-primary mb-1 text-[10px] font-bold tracking-[0.2em] uppercase">
                  Viewing {chunks.length} of {totalChunks || chunks.length} knowledge fragments
                </p>
                {hasMoreChunks ? (
                  <button
                    type="button"
                    onClick={handleLoadMoreChunks}
                    disabled={loadingMoreChunks}
                    className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/15 inline-flex items-center gap-2 rounded-full border px-4 py-2 text-xs font-bold tracking-[0.2em] uppercase transition disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loadingMoreChunks ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <ChevronsDown size={14} />
                    )}
                    Load more chunks
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-8">
          <div className="glass-card space-y-6 p-6">
            <h3 className="text-foreground border-glass-border/60 border-b pb-4 text-sm font-bold tracking-widest uppercase">
              Extraction Quality
            </h3>
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="dark:border-primary/30 dark:bg-primary/10 dark:text-primary rounded-md border border-teal-300 bg-teal-50/70 px-2 py-1 text-[10px] font-bold tracking-wider text-teal-900 uppercase">
                  Coverage {Math.round((doc.extraction_coverage_score ?? 0) * 100)}%
                </span>
                {doc.extraction_ocr_used ? (
                  <span className="rounded-md border border-orange-300 bg-orange-50/70 px-2 py-1 text-[10px] font-bold tracking-wider text-orange-900 uppercase dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-300">
                    OCR used
                  </span>
                ) : null}
                {doc.extraction_vision_used ? (
                  <span className="rounded-md border border-violet-300 bg-violet-50/70 px-2 py-1 text-[10px] font-bold tracking-wider text-violet-900 uppercase dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300">
                    Vision used
                  </span>
                ) : null}
              </div>
              <p className="font-mono text-xs text-slate-700 dark:text-slate-400">
                Method:{" "}
                <span className="text-foreground font-bold">{doc.extraction_method || "n/a"}</span>
              </p>
              <p className="font-mono text-xs text-slate-700 dark:text-slate-400">
                Embeddings:{" "}
                <span className="text-foreground font-bold">
                  {status?.embedding_provider || "pending"} / {status?.embedding_model || "pending"}
                </span>
              </p>
              {doc.extraction_warnings?.length ? (
                <div className="rounded-xl border border-amber-300 bg-amber-50/90 p-3 dark:border-amber-500/20 dark:bg-amber-500/10">
                  <p className="mb-2 text-[10px] font-bold tracking-wider text-amber-950 uppercase dark:text-amber-300">
                    Extraction Warnings
                  </p>
                  <ul className="space-y-1">
                    {doc.extraction_warnings.map((warning) => (
                      <li
                        key={warning}
                        className="font-mono text-xs text-[#78350f] dark:text-amber-200"
                      >
                        {warning}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>

          <div className="glass-card space-y-6 p-6">
            <h3 className="text-foreground border-glass-border/60 border-b pb-4 text-sm font-bold tracking-widest uppercase">
              Security & Integrity
            </h3>

            <div className="space-y-4">
              <div>
                <p className="mb-1.5 text-[10px] font-bold text-slate-600 uppercase">
                  SHA256 Fingerprint
                </p>
                <code className="theme-code-surface text-foreground/72 block rounded-xl p-3 font-mono text-[11px] leading-relaxed break-all">
                  {doc.sha256_hash}
                </code>
              </div>

              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <p className="mb-1.5 text-[10px] font-bold text-slate-600 uppercase">UUID</p>
                  <p className="text-foreground font-mono text-xs">
                    {doc.document_id.split("-")[0]}...
                  </p>
                </div>
                <div>
                  <p className="mb-1.5 text-[10px] font-bold text-slate-600 uppercase">
                    Tenant Isolation
                  </p>
                  <p className="flex items-center gap-1 text-xs font-bold text-green-500">
                    <Shield size={12} /> Secure
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-card space-y-6 p-6">
            <h3 className="text-foreground border-glass-border/60 border-b pb-4 text-sm font-bold tracking-widest uppercase">
              Version History
            </h3>
            <div className="space-y-4">
              {versions.length > 1 ? (
                <div className="space-y-3">
                  {versions.map((v) => (
                    <Link
                      key={v.document_id}
                      href={`/dashboard/documents/${v.document_id}`}
                      prefetch={false}
                      className={`flex items-center justify-between rounded-xl border p-3 transition-all ${
                        v.document_id === id
                          ? "border-primary/30 bg-primary/10 text-primary"
                          : "theme-chip text-slate-700 hover:border-white/10 dark:text-slate-400"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`h-2 w-2 rounded-full ${v.status === "indexed" ? "bg-green-500" : "bg-yellow-500"}`}
                        />
                        <div>
                          <p className="text-xs font-bold tracking-wider uppercase">v{v.version}</p>
                          <p className="font-mono text-[10px] opacity-60">
                            {new Date(v.created_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <ChevronRight size={14} />
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-700 italic dark:text-slate-400">
                  No other versions detected.
                </p>
              )}
              <div className="pt-2">
                <p className="text-[10px] leading-relaxed text-slate-700 italic dark:text-slate-500">
                  * New versions are automatically tracked when uploading a document with the same
                  filename but modified content.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
