"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  FolderOpen,
  Plus,
  FileText,
  RefreshCcw,
  ListChecks,
  X,
  Trash2,
  Database,
  Upload,
  Eye,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { fetchWithAuth, getApiBaseUrl } from "@/lib/api";
import UploadModal from "@/app/components/dashboard/documents/UploadModal";
import DocumentInspector from "@/app/components/dashboard/documents/DocumentInspector";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import ConfirmationModal from "@/app/components/ui/ConfirmationModal";
import EmptyState from "@/app/components/ui/EmptyState";
import { useHotkeys } from "@/app/hooks/useHotkeys";
import { readApiErrorMessage } from "@/app/lib/api/documents";
import { saveDocumentContentToDeepSpace } from "@/app/lib/deepspace-document-notes";
import toast from "react-hot-toast";
import { useAuth } from "@/app/context/AuthContext";
import { normalizeRole } from "@/lib/roles";

interface Document {
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  processing_progress: number;
  quarantined: boolean;
  information_yield: number | null;
  created_at: string;
  extraction_method?: string | null;
  extraction_coverage_score?: number | null;
  extraction_ocr_used?: boolean;
  extraction_vision_used?: boolean;
  extraction_warnings?: string[];
  updated_at?: string;
}

interface DocumentStatusUpdate {
  document_id: string;
  status: string;
  progress: number;
  updated_at?: string | null;
}

const PIPELINE_STAGE_ORDER: Record<string, number> = {
  queued: 0,
  downloading: 1,
  parsing: 2,
  chunking: 3,
  embedding: 4,
  completed: 5,
  indexed: 5,
  failed: 5,
  dead_lettered: 5,
};

const TERMINAL_DOCUMENT_STATUSES = new Set(["completed", "indexed", "failed", "dead_lettered"]);

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

function mergeDocumentStatus(current: Document, incoming: DocumentStatusUpdate): Document {
  const currentTime = current.updated_at ? Date.parse(current.updated_at) : NaN;
  const incomingTime = incoming.updated_at ? Date.parse(incoming.updated_at) : NaN;

  // Redis events can arrive late. Never let an older event move a document
  // backwards after the authoritative API has reported a newer state.
  if (Number.isFinite(currentTime) && Number.isFinite(incomingTime) && incomingTime < currentTime) {
    return current;
  }

  const currentStatus = current.status.toLowerCase();
  const incomingStatus = incoming.status.toLowerCase();
  if (
    !Number.isFinite(currentTime) &&
    !Number.isFinite(incomingTime) &&
    TERMINAL_DOCUMENT_STATUSES.has(currentStatus) &&
    !TERMINAL_DOCUMENT_STATUSES.has(incomingStatus)
  ) {
    return current;
  }

  if (
    incomingStatus !== currentStatus &&
    (PIPELINE_STAGE_ORDER[incomingStatus] ?? 0) < (PIPELINE_STAGE_ORDER[currentStatus] ?? 0)
  ) {
    return current;
  }

  return {
    ...current,
    status: incoming.status,
    processing_progress:
      incomingStatus === currentStatus
        ? Math.max(current.processing_progress, incoming.progress)
        : incoming.progress,
    updated_at: incoming.updated_at ?? current.updated_at,
  };
}

interface SupportedFormat {
  extension: string;
  category: string;
  extraction_method: string;
  needs_conversion: boolean;
}

interface SupportedFormatsResponse {
  total_formats: number;
  legacy_conversion_enabled: boolean;
  items: SupportedFormat[];
}

type PendingDocumentAction = {
  type: "delete" | "reingest";
  id: string;
  filename: string;
};

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [showFormats, setShowFormats] = useState(false);
  const [supportedFormats, setSupportedFormats] = useState<SupportedFormatsResponse | null>(null);
  const [inspectorTarget, setInspectorTarget] = useState<{ id: string; name: string } | null>(null);
  const [rawViewerTarget, setRawViewerTarget] = useState<{ id: string; name: string } | null>(null);
  const [rawFileUrl, setRawFileUrl] = useState<string | null>(null);
  const [rawFileContentType, setRawFileContentType] = useState<string | null>(null);
  const [rawTextContent, setRawTextContent] = useState<string | null>(null);
  const [isRawLoading, setIsRawLoading] = useState(false);
  const [viewerMode, setViewerMode] = useState<"raw" | "text">("raw");
  const [selection, setSelection] = useState<{ text: string; x: number; y: number } | null>(null);
  const [pasteDialogOpen, setPasteDialogOpen] = useState(false);
  const [pasteDraft, setPasteDraft] = useState("");
  const [rawLoadingPhase, setRawLoadingPhase] = useState<"secure" | "text" | "ready">("secure");
  const [mounted, setMounted] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingDocumentAction | null>(null);
  const [documentActionBusy, setDocumentActionBusy] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const { user } = useAuth();
  const normalizedRoles = user?.roles.map(normalizeRole) ?? [];
  const canManageDocuments = normalizedRoles.some((role) =>
    ["admin", "editor", "user"].includes(role),
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchDocuments = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const res = (await fetchWithAuth("/documents")) as Response;
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.items);
        setError(null);
      } else {
        setDocuments([]);
        setError(
          res.status === 401
            ? "Session expired. Redirecting to login..."
            : "Failed to load documents.",
        );
      }
    } catch (error) {
      console.error("Failed to fetch documents", error);
      setDocuments([]);
      setError("Failed to load documents.");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  // Real-time updates via SSE
  useEffect(() => {
    let cancelled = false;
    let eventSource: EventSource | null = null;

    const connect = async () => {
      try {
        const ticketResponse = (await fetchWithAuth("/documents/events/ticket")) as Response;
        if (!ticketResponse.ok || cancelled) return;
        const payload = (await ticketResponse.json()) as { ticket?: string };
        if (!payload.ticket || cancelled) return;

        const streamUrl = `${getApiBaseUrl().replace(/\/+$/, "")}/documents/events/stream?ticket=${encodeURIComponent(payload.ticket)}`;
        eventSource = new EventSource(streamUrl);
        eventSource.onmessage = (event) => {
          try {
            const update = JSON.parse(event.data) as DocumentStatusUpdate;
            setDocuments((prev) =>
              prev.map((doc) =>
                doc.document_id === update.document_id ? mergeDocumentStatus(doc, update) : doc,
              ),
            );
          } catch (err) {
            console.error("SSE parse error:", err);
          }
        };
        eventSource.onerror = (err) => {
          console.error("SSE connection error:", err);
          eventSource?.close();
        };
      } catch (err) {
        if (!cancelled) console.error("Failed to establish document event stream:", err);
      }
    };

    void connect();
    return () => {
      cancelled = true;
      eventSource?.close();
    };
  }, []);

  // SSE is the fast path, but this authoritative refresh repairs a missed or
  // unauthorized stream without making the page appear stuck indefinitely.
  const hasActiveDocuments = documents.some(
    (doc) => !TERMINAL_DOCUMENT_STATUSES.has(doc.status.toLowerCase()),
  );
  useEffect(() => {
    if (!hasActiveDocuments) return;
    const intervalId = window.setInterval(() => {
      void fetchDocuments(false);
    }, 4000);
    return () => window.clearInterval(intervalId);
  }, [hasActiveDocuments]);

  useEffect(() => {
    const fetchSupportedFormats = async () => {
      try {
        const response = (await fetchWithAuth("/documents/supported-formats")) as Response;
        if (!response.ok) return;
        const data = (await response.json()) as SupportedFormatsResponse;
        setSupportedFormats(data);
      } catch (error) {
        console.error("Failed to load supported format list", error);
      }
    };
    fetchSupportedFormats();
  }, []);

  const openRawViewer = async (id: string, name: string) => {
    if (rawFileUrl) URL.revokeObjectURL(rawFileUrl);
    setRawViewerTarget({ id, name });
    setIsRawLoading(true);
    setRawTextContent(null);
    setRawFileUrl(null);
    setRawFileContentType(null);
    setRawLoadingPhase("secure");
    setViewerMode("raw"); // Default to the original source file
    try {
      // Fetch both for seamless switching
      const [downloadRes, fullTextRes] = await Promise.all([
        fetchWithAuth(`/documents/${id}/download`),
        fetchWithAuth(`/documents/${id}/full-text`),
      ]);

      if (downloadRes.ok) {
        const contentType = downloadRes.headers.get("content-type") || "";
        if (contentType) {
          const blob = await (downloadRes as Response).blob();
          setRawFileUrl(URL.createObjectURL(blob));
          setRawFileContentType(contentType);
        }
      }

      setRawLoadingPhase("text");
      if (fullTextRes.ok) {
        const data = await (fullTextRes as Response).json();
        setRawTextContent(data.content);
        // If PDF failed, default to text mode
        if (!downloadRes.ok) setViewerMode("text");
      }
    } catch (err) {
      console.error("Error loading raw document", err);
    } finally {
      setRawLoadingPhase("ready");
      setIsRawLoading(false);
    }
  };

  const saveToNotes = async (mode: "full" | "selection" = "full", customText?: string) => {
    if (!rawViewerTarget) return;
    setIsRawLoading(true);
    try {
      let finalContent = "";
      let titlePrefix = "Research";

      const selectedText = customText?.trim() || selection?.text?.trim();
      if (selectedText) {
        finalContent = textToSafeNoteHtml(selectedText);
        titlePrefix = "Highlight";
      } else if (mode === "selection") {
        try {
          const text = await navigator.clipboard.readText();
          if (!text) throw new Error("Clipboard empty");
          finalContent = textToSafeNoteHtml(text);
          titlePrefix = "Insight";
        } catch {
          setPasteDialogOpen(true);
          setIsRawLoading(false);
          return;
        }
      } else {
        // Use pre-fetched text if available
        if (rawTextContent) {
          finalContent = textToSafeNoteHtml(rawTextContent);
        } else {
          const res = await fetchWithAuth(`/documents/${rawViewerTarget.id}/full-text`);
          if (!res.ok) throw new Error("Failed to fetch source text");
          const data = await (res as Response).json();
          finalContent = textToSafeNoteHtml(data.content);
        }
      }

      await saveDocumentContentToDeepSpace({
        title: `${titlePrefix}: ${rawViewerTarget.name}`,
        contentHtml: finalContent,
      });
      setSelection(null);
      setPasteDialogOpen(false);
      setPasteDraft("");
      toast.success("Content added to your active DeepSpace note.");
    } catch (err) {
      console.error("Failed to save note", err);
      toast.error(err instanceof Error ? err.message : "Unable to send content to notes.");
    } finally {
      setIsRawLoading(false);
    }
  };

  const handlePasteSelection = async () => {
    if (selection?.text) {
      await saveToNotes("selection", selection.text);
      return;
    }
    await saveToNotes("selection");
  };

  const handleTextSelection = () => {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      setSelection(null);
      return;
    }

    const text = sel.toString().trim();
    if (!text || text.length < 3) {
      setSelection(null);
      return;
    }

    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    setSelection({
      text,
      x: rect.left + rect.width / 2,
      y: rect.top - 12,
    });
  };

  const closeRawViewer = () => {
    if (rawFileUrl) URL.revokeObjectURL(rawFileUrl);
    setRawViewerTarget(null);
    setRawFileUrl(null);
    setRawFileContentType(null);
    setPasteDialogOpen(false);
    setPasteDraft("");
  };

  const downloadRawFile = () => {
    if (!rawFileUrl || !rawViewerTarget) return;
    const anchor = document.createElement("a");
    anchor.href = rawFileUrl;
    anchor.download = rawViewerTarget.name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  const deleteDocument = (id: string, filename: string) => {
    setPendingAction({ type: "delete", id, filename });
  };

  const reingestDocument = (id: string, filename: string) => {
    setPendingAction({ type: "reingest", id, filename });
  };

  const executeDocumentAction = async () => {
    if (!pendingAction) return;
    const action = pendingAction;
    setDocumentActionBusy(true);
    try {
      if (action.type === "delete") {
        const res = (await fetchWithAuth(`/documents/${action.id}`, {
          method: "DELETE",
        })) as Response;
        if (res.ok) {
          setDocuments((prev) => prev.filter((d) => d.document_id !== action.id));
          toast.success(`"${action.filename}" deleted.`);
        } else {
          toast.error(await readApiErrorMessage(res, "Failed to delete document."));
        }
      } else {
        const res = (await fetchWithAuth(`/documents/${action.id}/reingest`, {
          method: "POST",
        })) as Response;
        if (res.ok) {
          await fetchDocuments(false);
          toast.success(`"${action.filename}" queued for re-ingestion.`);
        } else {
          toast.error(await readApiErrorMessage(res, "Failed to re-ingest document."));
        }
      }
    } catch (err) {
      console.error(err);
      toast.error(err instanceof Error ? err.message : "The document action failed.");
    } finally {
      setDocumentActionBusy(false);
      setPendingAction(null);
    }
  };

  useHotkeys([
    {
      combo: { key: "u", ctrlOrCmd: true },
      handler: (e) => {
        e.preventDefault();
        setIsUploadOpen(true);
      },
    },
  ]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const statusColors: Record<string, string> = {
    queued: "!text-primary !bg-primary/5 !border-primary/20",
    downloading: "!text-warning !bg-warning/5 !border-warning/20",
    parsing: "!text-accent !bg-accent/5 !border-accent/20",
    chunking: "!text-primary !bg-primary/10 !border-primary/20",
    embedding: "!text-primary !bg-primary/15 !border-primary/30",
    completed: "!text-emerald-500 !bg-emerald-500/5 !border-emerald-500/20",
    indexed: "!text-emerald-500 !bg-emerald-500/5 !border-emerald-500/20",
    failed: "!text-danger !bg-danger/5 !border-danger/20",
    dead_lettered: "!text-foreground/40 !bg-foreground/5 !border-foreground/10",
  };

  return (
    <div className="space-y-10">
      <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
        <DashboardSectionHeader
          title="Documents"
          subtitle="Neural Intelligence Node Matrix"
          icon={FileText}
          accentClassName="bg-blue-500 text-blue-500"
          accentGlowClassName="shadow-[0_0_20px_rgba(59,130,246,0.4)]"
          actions={
            <>
              <button
                onClick={() => setShowFormats(true)}
                className="theme-pill hover-yellow border-accent/10 h-12 px-6 transition-all"
              >
                <ListChecks size={18} className="stroke-[2.5]" />
                <span className="font-bold">Protocol Matrix</span>
              </button>
              <button
                onClick={() => fetchDocuments()}
                disabled={loading}
                className="bg-foreground/5 text-foreground/40 hover:text-primary hover:bg-primary/10 border-glass-border flex h-12 w-12 items-center justify-center rounded-2xl border transition-all hover:scale-105 disabled:opacity-50"
              >
                <RefreshCcw size={20} className={`stroke-[2.5] ${loading ? "animate-spin" : ""}`} />
              </button>
              <button
                onClick={() => setIsUploadOpen(true)}
                className="bg-primary text-primary-foreground shadow-primary/20 flex h-12 items-center gap-3 rounded-2xl px-8 text-sm font-black tracking-widest uppercase shadow-xl transition-all hover:scale-[1.03] hover:brightness-110 active:scale-95"
              >
                <Upload size={18} className="stroke-[2.5]" />
                Ingest Source
              </button>
            </>
          }
        />
      </motion.div>

      {loading ? (
        <div className="theme-panel divide-glass-border divide-y">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex animate-pulse items-center gap-6 p-6">
              <div className="bg-foreground/5 h-10 w-10 rounded-xl" />
              <div className="flex-1 space-y-2">
                <div className="bg-foreground/5 h-4 w-1/4 rounded" />
                <div className="bg-foreground/5 h-3 w-1/6 rounded" />
              </div>
              <div className="bg-foreground/5 h-6 w-20 rounded-full" />
            </div>
          ))}
        </div>
      ) : error ? (
        <EmptyState
          icon={<FolderOpen size={28} />}
          title="Documents unavailable"
          description={error}
        />
      ) : documents.length > 0 ? (
        <div className="theme-panel overflow-hidden">
          {/* Desktop Table View */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-left">
              <thead className="text-foreground/40 border-glass-border border-b text-[10px] font-black tracking-[0.2em] uppercase">
                <tr>
                  <th className="px-6 py-5">Source Node</th>
                  <th className="px-6 py-5">Status Pipeline</th>
                  <th className="px-6 py-5">Intelligence Yield</th>
                  <th className="px-6 py-5 text-right">Size</th>
                  <th className="px-6 py-5 text-right">Indexed At</th>
                  <th className="px-6 py-5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-glass-border divide-y">
                {documents.map((doc) => (
                  <tr
                    key={doc.document_id}
                    className="group hover:bg-primary/[0.02] transition-colors"
                  >
                    <td className="px-6 py-5">
                      <div className="flex items-center gap-4">
                        <div className="bg-primary/5 text-primary border-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border">
                          <FileText size={18} className="stroke-[2.5]" />
                        </div>
                        <div className="min-w-0">
                          <Link
                            href={`/dashboard/documents/${doc.document_id}`}
                            prefetch={false}
                            className="text-foreground hover:text-primary focus-visible:ring-primary/50 block truncate text-sm leading-tight font-bold transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                            aria-label={`Open ${doc.filename}`}
                          >
                            {doc.filename}
                          </Link>
                          <p className="text-foreground/35 mt-1 text-[10px] font-bold tracking-widest uppercase">
                            {doc.content_type.split("/")[1] || "DOC"}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex items-center gap-3">
                        {doc.quarantined ? (
                          <span className="theme-pill !bg-danger/10 !border-danger/20 !text-danger">
                            Quarantined
                          </span>
                        ) : (
                          <span
                            className={`theme-pill border px-2.5 py-1 text-[10px] font-black tracking-widest uppercase shadow-sm ${statusColors[doc.status] || "!text-foreground/40 !bg-foreground/5 !border-foreground/10"}`}
                          >
                            {doc.status}
                          </span>
                        )}
                        <span className="text-foreground/30 hidden text-[11px] font-bold tabular-nums sm:inline">
                          {doc.processing_progress}%
                        </span>
                      </div>
                      <p className="text-foreground/35 mt-2 text-[10px] font-bold tracking-[0.18em] uppercase">
                        {doc.status === "indexed"
                          ? "Pipeline complete"
                          : `${doc.status} in progress`}
                      </p>
                      {(doc.processing_progress > 0 ||
                        doc.status === "queued" ||
                        doc.status === "downloading") && (
                        <div className="bg-foreground/5 mt-3 h-1.5 w-full max-w-[100px] overflow-hidden rounded-full">
                          <div
                            className="bg-primary h-full rounded-full shadow-[0_0_10px_rgba(var(--primary),0.3)] transition-all duration-700"
                            style={{ width: `${doc.processing_progress}%` }}
                          />
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="theme-pill !bg-primary/5 !border-primary/20 !text-primary/70">
                          {Math.round((doc.extraction_coverage_score ?? 0) * 100)}%
                        </span>
                        {doc.extraction_ocr_used && (
                          <span className="theme-pill !bg-warning/10 !border-warning/20 !text-warning">
                            OCR
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-foreground/40 px-6 py-5 text-right font-mono text-[11px] font-bold">
                      {formatBytes(doc.size_bytes)}
                    </td>
                    <td className="text-foreground/40 px-6 py-5 text-right text-[11px] font-bold">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-5 text-right">
                      <div className="flex items-center justify-end gap-2 opacity-40 transition-opacity group-hover:opacity-100">
                        <button
                          onClick={() => openRawViewer(doc.document_id, doc.filename)}
                          className="text-foreground/40 hover:text-primary hover:bg-primary/10 rounded-xl p-2.5 transition-all"
                          title="View Raw Document"
                        >
                          <Eye size={17} className="stroke-[2.5]" />
                        </button>
                        <button
                          onClick={() =>
                            setInspectorTarget({ id: doc.document_id, name: doc.filename })
                          }
                          className="text-foreground/40 hover:text-primary hover:bg-primary/10 rounded-xl p-2.5 transition-all"
                          title="Inspect Metadata"
                        >
                          <Database size={17} className="stroke-[2.5]" />
                        </button>
                        {canManageDocuments &&
                          (doc.status === "failed" || doc.status === "dead_lettered") && (
                          <button
                            onClick={() => reingestDocument(doc.document_id, doc.filename)}
                            className="text-foreground/40 rounded-xl p-2.5 transition-all hover:bg-emerald-500/10 hover:text-emerald-500"
                            title="Retry Vectorization"
                          >
                            <RefreshCcw size={17} className="stroke-[2.5]" />
                          </button>
                        )}
                        {canManageDocuments && (
                          <button
                            onClick={() => deleteDocument(doc.document_id, doc.filename)}
                            className="text-foreground/40 hover:text-danger hover:bg-danger/10 rounded-xl p-2.5 transition-all"
                            title="Delete document"
                            aria-label={`Delete ${doc.filename}`}
                          >
                            <Trash2 size={17} className="stroke-[2.5]" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile Card View */}
          <div className="divide-glass-border space-y-4 divide-y md:hidden">
            {documents.map((doc) => (
              <div key={doc.document_id} className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="bg-primary/5 text-primary border-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border">
                      <FileText size={18} className="stroke-[2.5]" />
                    </div>
                    <div className="min-w-0">
                      <Link
                        href={`/dashboard/documents/${doc.document_id}`}
                        prefetch={false}
                        className="text-foreground hover:text-primary focus-visible:ring-primary/50 block truncate text-sm leading-tight font-bold transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                        aria-label={`Open ${doc.filename}`}
                      >
                        {doc.filename}
                      </Link>
                      <div className="mt-1 flex items-center gap-2">
                        <span className="text-foreground/35 text-[10px] font-bold tracking-widest uppercase">
                          {doc.content_type.split("/")[1] || "DOC"}
                        </span>
                        <span className="text-foreground/20 text-[10px]">•</span>
                        <span className="text-foreground/35 text-[10px] font-bold">
                          {formatBytes(doc.size_bytes)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => openRawViewer(doc.document_id, doc.filename)}
                      aria-label={`View ${doc.filename}`}
                      className="text-foreground/40 bg-foreground/5 flex h-9 w-9 items-center justify-center rounded-lg"
                    >
                      <Eye size={15} />
                    </button>
                    <button
                      onClick={() =>
                        setInspectorTarget({ id: doc.document_id, name: doc.filename })
                      }
                      aria-label={`Inspect ${doc.filename}`}
                      className="text-foreground/40 bg-foreground/5 flex h-9 w-9 items-center justify-center rounded-lg"
                    >
                      <Database size={15} />
                    </button>
                    {canManageDocuments &&
                      (doc.status === "failed" || doc.status === "dead_lettered") && (
                        <button
                          onClick={() => reingestDocument(doc.document_id, doc.filename)}
                          aria-label={`Re-ingest ${doc.filename}`}
                          className="text-foreground/40 bg-emerald-500/5 flex h-9 w-9 items-center justify-center rounded-lg"
                        >
                          <RefreshCcw size={15} />
                        </button>
                      )}
                    {canManageDocuments && (
                      <button
                        onClick={() => deleteDocument(doc.document_id, doc.filename)}
                        aria-label={`Delete ${doc.filename}`}
                        className="text-foreground/40 bg-danger/5 flex h-9 w-9 items-center justify-center rounded-lg"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {doc.quarantined ? (
                    <span className="theme-pill !bg-danger/10 !border-danger/20 !text-danger text-[10px]">
                      Quarantined
                    </span>
                  ) : (
                    <span
                      className={`theme-pill border px-2.5 py-1 text-[9px] font-black tracking-widest uppercase ${statusColors[doc.status] || "!text-foreground/40 !bg-foreground/5 !border-foreground/10"}`}
                    >
                      {doc.status}
                    </span>
                  )}
                  <span className="theme-pill !bg-primary/5 !border-primary/20 !text-primary/70 text-[10px]">
                    Yield: {Math.round((doc.extraction_coverage_score ?? 0) * 100)}%
                  </span>
                  <span className="text-foreground/40 ml-auto text-[10px] font-bold">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <EmptyState
            icon={<FolderOpen size={48} className="text-primary opacity-20" />}
            title="Knowledge Base Empty"
            description="Start building your intelligence engine by uploading your first supported source file."
            action={
              <button
                onClick={() => setIsUploadOpen(true)}
                className="bg-primary text-primary-foreground shadow-primary/20 mt-4 flex h-10 items-center gap-2 rounded-xl px-6 text-sm font-bold shadow-lg transition hover:scale-105 active:scale-95"
              >
                <Plus size={16} className="stroke-[3]" />
                <span>Upload Document</span>
              </button>
            }
          />
        </motion.div>
      )}

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={() => fetchDocuments(false)}
      />

      <DocumentInspector
        isOpen={!!inspectorTarget}
        documentId={inspectorTarget?.id ?? null}
        documentName={inspectorTarget?.name ?? ""}
        onClose={() => setInspectorTarget(null)}
        onDeleted={() => {
          setDocuments((prev) => prev.filter((d) => d.document_id !== inspectorTarget?.id));
          setInspectorTarget(null);
        }}
      />

      <ConfirmationModal
        isOpen={pendingAction !== null}
        onClose={() => {
          if (!documentActionBusy) setPendingAction(null);
        }}
        onConfirm={executeDocumentAction}
        title={pendingAction?.type === "delete" ? "Delete document?" : "Re-ingest document?"}
        message={
          pendingAction?.type === "delete"
            ? `Are you sure you want to delete “${pendingAction.filename}”? This removes it from the workspace.`
            : `Re-ingest “${pendingAction?.filename ?? "this document"}”? Extraction and indexing will restart from the beginning.`
        }
        confirmLabel={pendingAction?.type === "delete" ? "Delete document" : "Re-ingest document"}
        variant={pendingAction?.type === "delete" ? "danger" : "warning"}
        loading={documentActionBusy}
      />

      {/* Raw Document Viewer Drawer */}
      {mounted &&
        typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {rawViewerTarget && (
              <>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  onClick={closeRawViewer}
                  className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm"
                />
                <motion.div
                  ref={drawerRef}
                  initial={{ x: "100%" }}
                  animate={{ x: 0 }}
                  exit={{ x: "100%" }}
                  onMouseUp={handleTextSelection}
                  transition={{ type: "spring", damping: 30, stiffness: 300 }}
                  className="border-glass-border/30 bg-surface-0 !fixed !top-0 !right-0 !bottom-0 !left-auto !z-[70] !m-0 flex !h-[100svh] w-full flex-col overflow-hidden !rounded-none border-l shadow-[-20px_0_80px_rgba(0,0,0,0.5)] backdrop-blur-3xl sm:max-w-[75vw] xl:max-w-[50vw]"
                >
                  <AnimatePresence>
                    {selection && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.8, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.8, y: 10 }}
                        style={{
                          position: "fixed",
                          left: selection.x,
                          top: selection.y,
                          transform: "translateX(-50%) translateY(-100%)",
                          zIndex: 100,
                        }}
                        className="flex items-center gap-2"
                      >
                        <button
                          onClick={() => saveToNotes("selection", selection.text)}
                          className="bg-primary shadow-primary/20 flex items-center gap-2 rounded-full px-4 py-2 text-[10px] font-black tracking-widest text-white uppercase shadow-xl ring-4 ring-black/50 backdrop-blur-md transition-all hover:scale-105 active:scale-95"
                        >
                          <Plus size={14} className="stroke-[3]" />
                          <span>Add to Note</span>
                        </button>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div className="border-glass-border/60 bg-surface-0/40 flex items-center justify-between border-b px-6 py-5 backdrop-blur-xl">
                    <div className="flex items-center gap-4">
                      <div className="bg-primary shadow-primary/20 flex h-11 w-11 items-center justify-center rounded-2xl text-white shadow-lg">
                        <Eye size={22} className="stroke-[2.5]" />
                      </div>
                      <div>
                        <h3 className="text-foreground text-base font-black tracking-tight">
                          {rawViewerTarget.name}
                        </h3>
                        <div className="mt-1 flex items-center gap-1">
                          <button
                            onClick={() => setViewerMode("raw")}
                            className={`rounded-md px-2 py-0.5 text-[9px] font-black tracking-widest uppercase transition-all ${viewerMode === "raw" ? "bg-primary text-white" : "bg-foreground/5 text-foreground/40 hover:bg-foreground/10"}`}
                          >
                            Source File
                          </button>
                          <button
                            onClick={() => setViewerMode("text")}
                            className={`rounded-md px-2 py-0.5 text-[9px] font-black tracking-widest uppercase transition-all ${viewerMode === "text" ? "bg-primary text-white" : "bg-foreground/5 text-foreground/40 hover:bg-foreground/10"}`}
                          >
                            Intelligence View
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="bg-foreground/5 flex items-center rounded-xl p-1 backdrop-blur-sm">
                        <button
                          onClick={handlePasteSelection}
                          disabled={isRawLoading}
                          className="hover:bg-primary text-foreground/70 flex h-9 items-center gap-2 rounded-lg px-3 text-[10px] font-black tracking-wider uppercase transition-all hover:text-white disabled:opacity-50"
                          title="Paste copied text or save the selected Intelligence View text"
                        >
                          <Plus size={14} className="stroke-[2.5]" />
                          <span>Paste Selection</span>
                        </button>
                        <div className="bg-foreground/10 mx-1 h-4 w-px" />
                        <button
                          onClick={() => saveToNotes("full")}
                          disabled={isRawLoading}
                          className="hover:bg-primary text-foreground/70 flex h-9 items-center gap-2 rounded-lg px-3 text-[10px] font-black tracking-wider uppercase transition-all hover:text-white disabled:opacity-50"
                        >
                          {isRawLoading ? (
                            <RefreshCcw size={14} className="animate-spin" />
                          ) : (
                            <Database size={14} className="stroke-[2.5]" />
                          )}
                          <span>Save Full Doc</span>
                        </button>
                      </div>
                        <button
                          onClick={closeRawViewer}
                        className="bg-foreground/5 text-foreground/40 hover:text-danger hover:bg-danger/10 flex h-10 w-10 items-center justify-center rounded-xl transition-all"
                      >
                          <X size={22} className="stroke-[2.5]" />
                        </button>
                    </div>
                  </div>
                  <div className="relative flex-1 overflow-hidden bg-white/5">
                    {isRawLoading ? (
                      <div className="flex h-full flex-col items-center justify-center gap-6 p-8 text-center">
                        <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-primary/20 bg-primary/5">
                          <div className="absolute inset-1 animate-spin rounded-full border-2 border-transparent border-t-primary border-r-primary/40" />
                          <Eye size={25} className="text-primary" />
                        </div>
                        <div className="w-full max-w-sm space-y-3">
                          <p className="text-foreground text-sm font-black tracking-wide">
                            Preparing secure preview
                          </p>
                          <div className="grid grid-cols-3 gap-2 text-[9px] font-black tracking-widest uppercase">
                            {[
                              ["secure", "Secure fetch"],
                              ["text", "Text index"],
                              ["ready", "Preview"],
                            ].map(([phase, label]) => (
                              <div
                                key={phase}
                                className={`rounded-lg border px-2 py-2 transition-colors ${
                                  rawLoadingPhase === phase
                                    ? "border-primary/40 bg-primary/10 text-primary"
                                    : "border-foreground/10 text-foreground/30"
                                }`}
                              >
                                <span
                                  className={`mx-auto mb-1 block h-1.5 w-1.5 rounded-full ${rawLoadingPhase === phase ? "animate-pulse bg-primary" : "bg-foreground/20"}`}
                                />
                                {label}
                              </div>
                            ))}
                          </div>
                          <p className="text-foreground/40 text-[10px] font-bold tracking-widest uppercase">
                            {rawLoadingPhase === "secure"
                              ? "Fetching original file securely"
                              : "Loading extracted text without reloading the page"}
                          </p>
                        </div>
                      </div>
                    ) : viewerMode === "raw" && rawFileUrl ? (
                      rawFileContentType?.startsWith("image/") ? (
                        <div className="flex h-full items-center justify-center overflow-auto p-8">
                          {/* Blob URLs cannot be optimized by Next Image. */}
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={rawFileUrl}
                            alt={`Original ${rawViewerTarget.name}`}
                            className="max-h-full max-w-full object-contain"
                          />
                        </div>
                      ) : rawFileContentType?.includes("pdf") ? (
                        <iframe
                          src={rawFileUrl}
                          className="h-full w-full border-none"
                          title="Original Document"
                        />
                      ) : (
                        <div className="flex h-full flex-col items-center justify-center gap-5 p-8 text-center">
                          <Database size={42} className="text-primary/40" />
                          <div>
                            <p className="text-foreground text-sm font-bold">
                              Source file is ready to download
                            </p>
                            <p className="text-foreground/40 mt-2 max-w-sm text-xs leading-relaxed">
                              This file type cannot be rendered safely in the browser. Download the
                              original file to open it with its native application.
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={downloadRawFile}
                            className="bg-primary text-primary-foreground rounded-xl px-5 py-3 text-xs font-black tracking-widest uppercase shadow-lg transition hover:brightness-110"
                          >
                            Download source file
                          </button>
                        </div>
                      )
                    ) : viewerMode === "text" && rawTextContent ? (
                      <div className="bg-surface-0 h-full overflow-y-auto px-12 py-16">
                        <div className="mx-auto max-w-3xl">
                          <pre className="text-foreground/90 selection:bg-primary/40 max-w-none whitespace-pre-wrap font-mono text-sm leading-7 selection:text-white">
                            {rawTextContent}
                          </pre>
                        </div>
                      </div>
                    ) : (
                      <div className="flex h-full items-center justify-center">
                        <p className="text-foreground/30 text-xs font-bold tracking-widest uppercase">
                          No Intelligence View Available
                        </p>
                      </div>
                    )}
                  </div>
                </motion.div>

                <AnimatePresence>
                  {pasteDialogOpen && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/40 p-5 backdrop-blur-sm"
                    >
                      <motion.form
                        initial={{ opacity: 0, y: 12, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 12, scale: 0.98 }}
                        onSubmit={(event) => {
                          event.preventDefault();
                          if (pasteDraft.trim()) void saveToNotes("selection", pasteDraft);
                        }}
                        className="bg-surface-0 border-glass-border w-full max-w-lg rounded-2xl border p-5 shadow-2xl"
                      >
                        <div className="mb-4 flex items-start justify-between gap-4">
                          <div>
                            <h4 className="text-foreground text-sm font-black">Paste selection</h4>
                            <p className="text-foreground/50 mt-1 text-xs">
                              Paste text here when the browser blocks direct clipboard access.
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => setPasteDialogOpen(false)}
                            className="text-foreground/40 hover:text-foreground rounded-lg p-1"
                            aria-label="Close paste dialog"
                          >
                            <X size={18} />
                          </button>
                        </div>
                        <textarea
                          autoFocus
                          value={pasteDraft}
                          onChange={(event) => setPasteDraft(event.target.value)}
                          placeholder="Paste copied text here..."
                          rows={8}
                          className="bg-foreground/[0.03] text-foreground placeholder:text-foreground/30 focus:border-primary/60 w-full resize-y rounded-xl border border-foreground/10 p-3 text-sm outline-none"
                        />
                        <div className="mt-4 flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setPasteDialogOpen(false)}
                            className="text-foreground/60 hover:text-foreground rounded-xl px-4 py-2 text-xs font-bold"
                          >
                            Cancel
                          </button>
                          <button
                            type="submit"
                            disabled={!pasteDraft.trim() || isRawLoading}
                            className="bg-primary text-primary-foreground rounded-xl px-4 py-2 text-xs font-black uppercase disabled:opacity-40"
                          >
                            Save to active note
                          </button>
                        </div>
                      </motion.form>
                    </motion.div>
                  )}
                </AnimatePresence>
              </>
            )}
          </AnimatePresence>,
          document.body,
        )}

      {mounted &&
        typeof document !== "undefined" &&
        showFormats &&
        createPortal(
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setShowFormats(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-surface-0 border-glass-border relative max-h-[85vh] w-full max-w-2xl overflow-hidden rounded-3xl border p-8 shadow-2xl"
            >
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h3 className="text-foreground text-2xl font-extrabold tracking-tight">
                    Supported Formats
                  </h3>
                  <p className="text-foreground/40 mt-1 text-sm font-medium">
                    Native pipeline coverage coverage currently available.
                  </p>
                </div>
                <button
                  onClick={() => setShowFormats(false)}
                  className="bg-foreground/5 text-foreground/40 hover:text-foreground hover:bg-foreground/10 flex h-10 w-10 items-center justify-center rounded-xl transition-all"
                >
                  <X size={20} className="stroke-[2.5]" />
                </button>
              </div>

              <div className="border-glass-border bg-foreground/[0.01] max-h-[60vh] overflow-y-auto rounded-2xl border shadow-inner">
                <table className="w-full border-collapse text-left">
                  <thead className="bg-surface-0/80 border-glass-border sticky top-0 z-10 border-b backdrop-blur-sm">
                    <tr className="text-foreground/40 text-[10px] font-bold tracking-[0.2em] uppercase">
                      <th className="px-5 py-4">Extension</th>
                      <th className="px-5 py-4">Category</th>
                      <th className="px-5 py-4">Method</th>
                      <th className="px-5 py-4 text-right">Mode</th>
                    </tr>
                  </thead>
                  <tbody className="divide-glass-border divide-y">
                    {(supportedFormats?.items ?? []).map((item) => (
                      <tr
                        key={`${item.extension}-${item.extraction_method}`}
                        className="hover-yellow transition-colors"
                      >
                        <td className="text-primary px-5 py-4 font-mono text-[13px] font-bold">
                          {item.extension}
                        </td>
                        <td className="text-foreground/60 px-5 py-4 text-[13px] font-medium">
                          {item.category}
                        </td>
                        <td className="text-foreground/30 px-5 py-4 font-mono text-[11px] italic">
                          {item.extraction_method}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <span
                            className={`theme-pill ${
                              item.needs_conversion
                                ? "!text-warning !bg-warning/10 !border-warning/20"
                                : "!text-primary !bg-primary/10 !border-primary/20"
                            }`}
                          >
                            {item.needs_conversion ? "conversion" : "native"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          </div>,
          document.body,
        )}
    </div>
  );
}
