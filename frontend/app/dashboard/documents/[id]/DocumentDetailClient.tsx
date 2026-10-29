"use client";

// PDF page thumbnails are authenticated blob URLs, so Next Image optimization
// cannot process them. The native image element is intentional here.
/* eslint-disable @next/next/no-img-element */

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
  RotateCcw,
  GitCompare,
  Brain,
  MessageSquare,
  Link2,
  Pencil,
  Trash2,
  Tag,
  ZoomIn,
  ZoomOut,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";
import AverQelLoading from "@/app/components/ui/AverQelLoading";
import { useRealtimeEvents } from "@/lib/realtime";
import { hasDocumentOrganizationAdvancedAccess } from "@/lib/roles";
import {
  getDocumentStatusPollingInterval,
  getDocumentStatusRetryDelay,
  getRealtimeStatusRefreshDelay,
  isTerminalDocumentStatus,
} from "../_lib/status-polling";
import { saveDocumentContentToDeepSpace } from "@/app/lib/deepspace-document-notes";
import toast from "react-hot-toast";
import Link from "next/link";
import { averqelAlert, averqelConfirm, averqelPrompt } from "@/app/components/ui/AverQelDialogHost";

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

interface VersionDiffResponse {
  from_version: number;
  to_version: number;
  changed: boolean;
  unified_diff: string;
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
  security_scan_result: string | null;
  security_scan_reason: string | null;
  security_scanned_at: string | null;
  security_scan_required: boolean;
  total_chunk_count: number;
  embedded_chunk_count: number;
  recovery_available: boolean;
  recovery_stage: string | null;
  recovery_reason: string | null;
  last_checkpoint_at: string | null;
  remaining_chunk_count: number;
  resume_count: number;
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

interface QualityReport {
  extraction_method: string | null;
  extraction_coverage_score: number | null;
  ocr_used: boolean;
  vision_used: boolean;
  warnings: string[];
  total_chunks: number;
  low_quality_chunks: number;
  page_numbers: number[];
  missing_page_numbers: number[];
}

interface ClassificationHistoryItem {
  id: string;
  rule_name: string;
  source: string;
  status: string;
  actions: Record<string, boolean>;
  error_message?: string | null;
  created_at: string;
}

interface DocumentComment {
  id: string;
  content: string;
  user_id: string;
  created_at: string;
  mentions?: string[];
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

function extractMentionIds(value: string): string[] {
  return [...new Set(value.match(/@[0-9a-f]{8}-[0-9a-f-]{27,}/gi) ?? [])].map((value) =>
    value.slice(1),
  );
}

async function getDocumentApiErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.clone().json();
    const message = payload?.error?.message ?? payload?.detail ?? payload?.message;
    if (typeof message === "string" && message.trim()) return message.trim().slice(0, 300);
  } catch {
    // Keep a safe status-based fallback for non-JSON or malformed responses.
  }
  return `${fallback} (HTTP ${response.status})`;
}

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const { user } = useAuth();
  const canViewClassificationHistory = hasDocumentOrganizationAdvancedAccess(user?.roles);
  const [doc, setDoc] = useState<DocumentMetadata | null>(null);
  const [status, setStatus] = useState<DocumentStatus | null>(null);
  const [versions, setVersions] = useState<VersionHistory[]>([]);
  const [chunks, setChunks] = useState<ChunkPreview[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [hasMoreChunks, setHasMoreChunks] = useState(false);
  const [loadingMoreChunks, setLoadingMoreChunks] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoadError, setDetailLoadError] = useState<string | null>(null);
  const [chunksError, setChunksError] = useState<string | null>(null);
  const [fullTextLoading, setFullTextLoading] = useState(false);
  const [fullTextError, setFullTextError] = useState<string | null>(null);
  const [fullTextLoadedFor, setFullTextLoadedFor] = useState<string | null>(null);
  const [fullText, setFullText] = useState<string | null>(null);
  const [requestRetrySeconds, setRequestRetrySeconds] = useState(0);
  const [viewMode, setViewMode] = useState<"reader" | "technical">("reader");
  const [selection, setSelection] = useState<{ text: string; x: number; y: number } | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [showSecurityVerification, setShowSecurityVerification] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [versionDiff, setVersionDiff] = useState<VersionDiffResponse | null>(null);
  const [restoringVersion, setRestoringVersion] = useState<string | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [classificationHistory, setClassificationHistory] = useState<ClassificationHistoryItem[]>(
    [],
  );
  const [comments, setComments] = useState<DocumentComment[]>([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentBusy, setCommentBusy] = useState(false);
  const [aiAction, setAiAction] = useState<"summarize" | "extract" | "faqs" | "compare">(
    "summarize",
  );
  const [aiAnswer, setAiAnswer] = useState<string | null>(null);
  const [aiCitations, setAiCitations] = useState<Array<Record<string, unknown>>>([]);
  const [aiBusy, setAiBusy] = useState(false);
  const [thumbnailUrls, setThumbnailUrls] = useState<Record<number, string>>({});
  const [shareLink, setShareLink] = useState<{ id: string; token: string } | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const [previewScale, setPreviewScale] = useState(1);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const aiActionButtonRef = useRef<HTMLButtonElement>(null);
  const [aiActionMenuOpen, setAiActionMenuOpen] = useState(false);
  const detailRequestInFlightRef = useRef(false);
  const statusRequestInFlightRef = useRef(false);
  const fullTextRequestInFlightRef = useRef(false);
  const fullTextLoadedForRef = useRef<string | null>(null);
  const requestRetryAtRef = useRef(0);
  const terminalDataRefreshStartedRef = useRef(false);
  const realtimeStatusRefreshTimerRef = useRef<number | null>(null);
  const lastRealtimeStatusRefreshAtRef = useRef(0);

  const recordRequestCooldown = useCallback((response: Response) => {
    if (response.status !== 429 && response.status !== 503) return;
    const retryAt = Date.now() + getDocumentStatusRetryDelay(response, 5_000);
    requestRetryAtRef.current = Math.max(requestRetryAtRef.current, retryAt);
    setRequestRetrySeconds(Math.ceil((requestRetryAtRef.current - Date.now()) / 1000));
  }, []);

  const recordTransientCooldown = useCallback(() => {
    const retryAt = Date.now() + 10_000;
    requestRetryAtRef.current = Math.max(requestRetryAtRef.current, retryAt);
    setRequestRetrySeconds(Math.ceil((requestRetryAtRef.current - Date.now()) / 1000));
  }, []);

  useEffect(() => {
    if (requestRetrySeconds <= 0) return;
    const timer = window.setTimeout(() => {
      const remainingSeconds = Math.max(
        0,
        Math.ceil((requestRetryAtRef.current - Date.now()) / 1000),
      );
      setRequestRetrySeconds(remainingSeconds);
    }, 1_000);
    return () => window.clearTimeout(timer);
  }, [requestRetrySeconds]);

  const fetchChunks = useCallback(
    async (offset: number, append: boolean) => {
      if (!id) return false;
      if (Date.now() < requestRetryAtRef.current) {
        setChunksError("The service is busy. Wait for the retry timer before loading fragments.");
        return false;
      }
      try {
        const response = (await fetchWithAuth(
          `/documents/${id}/chunks?limit=${CHUNK_PAGE_SIZE}&offset=${offset}`,
          { timeoutMs: 60_000, silentTimeout: true, suppressErrorToast: true },
        )) as Response;
        if (!response.ok) {
          recordRequestCooldown(response);
          setChunksError(
            "Document fragments could not be loaded. Retry when the service is available.",
          );
          return false;
        }
        const data = (await response.json()) as ChunksResponse;
        setTotalChunks(data.total_chunks);
        setHasMoreChunks(data.has_more);
        setChunks((current) => (append ? [...current, ...data.chunks] : data.chunks));
        setChunksError(null);
        return true;
      } catch {
        recordTransientCooldown();
        setChunksError(
          "Document fragments could not be loaded. Retry when the service is available.",
        );
        return false;
      }
    },
    [id, recordRequestCooldown, recordTransientCooldown],
  );

  const fetchDocumentStatus = useCallback(async () => {
    if (!id || statusRequestInFlightRef.current) return null;
    if (Date.now() < requestRetryAtRef.current) return null;
    statusRequestInFlightRef.current = true;
    try {
      const response = (await fetchWithAuth(`/documents/${id}/status`, {
        timeoutMs: 60_000,
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      if (!response.ok) {
        recordRequestCooldown(response);
        return { response, status: null };
      }

      const nextStatus = (await response.json()) as DocumentStatus;
      setStatus(nextStatus);
      return { response, status: nextStatus };
    } catch {
      recordTransientCooldown();
      return null;
    } finally {
      statusRequestInFlightRef.current = false;
    }
  }, [id, recordRequestCooldown, recordTransientCooldown]);

  const loadFullText = useCallback(async () => {
    if (!id || fullTextRequestInFlightRef.current || fullTextLoadedForRef.current === id) return;
    if (Date.now() < requestRetryAtRef.current) {
      const seconds = Math.ceil((requestRetryAtRef.current - Date.now()) / 1000);
      setFullTextError(`The service asked us to wait ${seconds} seconds before retrying.`);
      return;
    }
    fullTextRequestInFlightRef.current = true;
    setFullTextLoading(true);
    setFullTextError(null);
    try {
      const response = (await fetchWithAuth(`/documents/${id}/full-text`, {
        timeoutMs: 60_000,
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      if (!response.ok) {
        recordRequestCooldown(response);
        setFullTextError(
          response.status === 429 || response.status === 503
            ? "The service is busy. Wait for the retry timer, then try again."
            : "Extracted text could not be loaded. Retry when the service is available.",
        );
        return;
      }
      const data = (await response.json()) as { content?: unknown };
      if (typeof data.content !== "string") {
        setFullTextError("The server returned an invalid extracted-text response.");
        return;
      }
      setFullText(data.content);
      fullTextLoadedForRef.current = id;
      setFullTextLoadedFor(id);
    } catch (error) {
      recordTransientCooldown();
      setFullTextError(
        error instanceof Error && error.name === "ApiRequestTimeoutError"
          ? "Loading extracted text timed out. Your document is still available; retry later."
          : "Extracted text could not be loaded. Check your connection and retry.",
      );
    } finally {
      fullTextRequestInFlightRef.current = false;
      setFullTextLoading(false);
    }
  }, [id, recordRequestCooldown, recordTransientCooldown]);

  const fetchData = useCallback(async () => {
    if (!id || detailRequestInFlightRef.current) return;
    if (Date.now() < requestRetryAtRef.current) {
      const seconds = Math.ceil((requestRetryAtRef.current - Date.now()) / 1000);
      setDetailLoadError(`The service asked us to wait ${seconds} seconds before retrying.`);
      return;
    }
    detailRequestInFlightRef.current = true;
    try {
      setDetailLoadError(null);
      const requestOptions = {
        timeoutMs: 60_000,
        silentTimeout: true,
        suppressErrorToast: true,
      };
      const statusPromise = fetchDocumentStatus();
      let metaResponse: Response | null = null;
      try {
        metaResponse = (await fetchWithAuth(`/documents/${id}`, requestOptions)) as Response;
      } catch {
        // Keep failures in the page state so callers do not produce unhandled
        // rejections or a duplicate global toast.
        recordTransientCooldown();
      }

      if (!metaResponse?.ok) {
        if (metaResponse) recordRequestCooldown(metaResponse);
        setDetailLoadError(
          metaResponse?.status === 429 || metaResponse?.status === 503
            ? "The service is busy. Wait for the retry timer, then retry the document details."
            : metaResponse?.status === 404
              ? "This document was not found or is no longer available to your account."
              : "Document details could not be loaded. Check your connection and retry.",
        );
        return;
      }

      let metadata: DocumentMetadata;
      try {
        metadata = (await metaResponse.json()) as DocumentMetadata;
      } catch {
        setDetailLoadError("The server returned invalid document details. Retry in a moment.");
        return;
      }
      setDoc(metadata);
      setLoading(false);

      const [statusResult] = await Promise.allSettled([statusPromise]);
      let partialFailure = false;
      const currentStatus =
        statusResult?.status === "fulfilled" ? (statusResult.value?.status ?? null) : null;
      if (currentStatus) {
        terminalDataRefreshStartedRef.current =
          isTerminalDocumentStatus(currentStatus.status) && !currentStatus.recovery_available;
      } else {
        partialFailure = true;
      }
      if (Date.now() < requestRetryAtRef.current) {
        setDetailLoadError(
          "The service is busy. Wait for the retry timer before loading more details.",
        );
        return;
      }

      const [chunksLoaded, qualityResult, commentsResult, classificationResult, versionsResult] =
        await Promise.all([
          fetchChunks(0, false).catch(() => false),
          (fetchWithAuth(`/documents/${id}/quality`, requestOptions) as Promise<Response>).catch(
            () => {
              recordTransientCooldown();
              return null;
            },
          ),
          (fetchWithAuth(`/documents/${id}/comments`, requestOptions) as Promise<Response>).catch(
            () => {
              recordTransientCooldown();
              return null;
            },
          ),
          canViewClassificationHistory
            ? (
                fetchWithAuth(
                  `/documents/organization/classification-rules/documents/${id}/history`,
                  requestOptions,
                ) as Promise<Response>
              ).catch(() => {
                recordTransientCooldown();
                return null;
              })
            : Promise.resolve(null),
          (fetchWithAuth(`/documents/${id}/versions`, requestOptions) as Promise<Response>).catch(
            () => {
              recordTransientCooldown();
              return null;
            },
          ),
        ]);

      if (!chunksLoaded) partialFailure = true;
      [qualityResult, commentsResult, classificationResult, versionsResult].forEach((response) => {
        if (response) recordRequestCooldown(response);
      });
      const readJson = async <T,>(response: Response | null): Promise<T | null> => {
        if (!response?.ok) return null;
        try {
          return (await response.json()) as T;
        } catch {
          return null;
        }
      };
      const [qualityData, commentsData, classificationData, versionsData] = await Promise.all([
        readJson<QualityReport>(qualityResult),
        readJson<DocumentComment[]>(commentsResult),
        classificationResult === null
          ? Promise.resolve(null)
          : readJson<{ items?: ClassificationHistoryItem[] }>(classificationResult),
        readJson<VersionsResponse>(versionsResult),
      ]);
      if (qualityData) setQuality(qualityData);
      else partialFailure = true;
      if (commentsData) setComments(commentsData);
      else partialFailure = true;
      if (classificationResult !== null) {
        if (classificationData) setClassificationHistory(classificationData.items ?? []);
        else partialFailure = true;
      }
      if (versionsData) setVersions(versionsData.versions);
      else partialFailure = true;

      setDetailLoadError(
        partialFailure
          ? "Some document details are temporarily unavailable. Retry to load the missing information."
          : null,
      );

      // Full text is a potentially large response. Do not request it while OCR,
      // extraction, or embedding is still in progress.
      if (
        currentStatus &&
        (currentStatus.status === "indexed" || currentStatus.status === "completed") &&
        !currentStatus?.recovery_available
      ) {
        void loadFullText();
      } else {
        setFullText(null);
        setFullTextError(null);
        setFullTextLoading(false);
      }
    } catch {
      recordTransientCooldown();
      setDetailLoadError(
        "Some document details could not be loaded. Retry when the service is available.",
      );
    } finally {
      detailRequestInFlightRef.current = false;
      setLoading(false);
    }
  }, [
    canViewClassificationHistory,
    fetchChunks,
    fetchDocumentStatus,
    id,
    loadFullText,
    recordRequestCooldown,
    recordTransientCooldown,
  ]);

  const refreshDocumentStatus = useCallback(async () => {
    const result = await fetchDocumentStatus();
    if (!result?.status) return result;

    const nextStatus = result.status;
    const pollInterval = getDocumentStatusPollingInterval(nextStatus);
    if (pollInterval !== null) {
      terminalDataRefreshStartedRef.current = false;
    } else if (
      isTerminalDocumentStatus(nextStatus.status) &&
      !nextStatus.recovery_available &&
      !terminalDataRefreshStartedRef.current
    ) {
      terminalDataRefreshStartedRef.current = true;
      await fetchData();
    }

    return result;
  }, [fetchData, fetchDocumentStatus]);

  useEffect(() => {
    if (!id || !quality?.page_numbers.length || !doc?.content_type.includes("pdf")) return;
    let cancelled = false;
    const controller = new AbortController();
    const createdUrls: string[] = [];
    const loadThumbnails = async () => {
      const pages = quality.page_numbers.slice(0, 12);
      const entries: (readonly [number, string] | null)[] = Array(pages.length).fill(null);
      let nextIndex = 0;
      const loadNext = async () => {
        while (!cancelled && nextIndex < pages.length) {
          const index = nextIndex++;
          const page = pages[index];
          if (page === undefined) continue;
          try {
            const response = (await fetchWithAuth(`/documents/${id}/pages/${page}/thumbnail`, {
              signal: controller.signal,
              timeoutMs: 20_000,
              silentTimeout: true,
              suppressErrorToast: true,
            })) as Response;
            if (!response.ok || cancelled) continue;
            const url = URL.createObjectURL(await response.blob());
            createdUrls.push(url);
            entries[index] = [page, url];
          } catch {
            // Thumbnails are optional; one failed page must not reject the group.
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(3, pages.length) }, () => loadNext()));
      if (!cancelled)
        setThumbnailUrls(
          Object.fromEntries(
            entries.filter((entry): entry is readonly [number, string] => entry !== null),
          ),
        );
    };
    void loadThumbnails();
    return () => {
      cancelled = true;
      controller.abort();
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [doc?.content_type, id, quality?.page_numbers]);

  useEffect(() => {
    if (!id || previewPage === null) return;
    let cancelled = false;
    // Preview loading state is intentionally synchronized with the selected page.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewText(null);
    void (async () => {
      try {
        const response = (await fetchWithAuth(`/documents/${id}/pages/${previewPage}`, {
          timeoutMs: 30_000,
          silentTimeout: true,
          suppressErrorToast: true,
        })) as Response;
        if (!response.ok) throw new Error("This page preview is unavailable.");
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.startsWith("image/")) {
          const nextUrl = URL.createObjectURL(await response.blob());
          if (cancelled) URL.revokeObjectURL(nextUrl);
          else
            setPreviewUrl((current) => {
              if (current) URL.revokeObjectURL(current);
              return nextUrl;
            });
        } else {
          const text = await response.text();
          if (!cancelled) {
            setPreviewUrl((current) => {
              if (current) URL.revokeObjectURL(current);
              return null;
            });
            setPreviewText(text);
          }
        }
      } catch (error) {
        if (!cancelled) {
          setPreviewUrl(null);
          setPreviewError(
            error instanceof Error ? error.message : "This page preview is unavailable.",
          );
        }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, previewPage]);

  const runAiAction = async () => {
    if (!id) return;
    setAiBusy(true);
    try {
      const response = (await fetchWithAuth(`/documents/${id}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: aiAction }),
        timeoutMs: 120_000,
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      if (!response.ok) {
        throw new Error(
          await getDocumentApiErrorMessage(response, "The document action could not be completed."),
        );
      }
      const data = (await response.json()) as {
        answer?: unknown;
        citations?: Array<Record<string, unknown>>;
      };
      setAiAnswer(
        typeof data.answer === "string" ? data.answer : JSON.stringify(data.answer, null, 2),
      );
      setAiCitations(Array.isArray(data.citations) ? data.citations : []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The document action failed.");
    } finally {
      setAiBusy(false);
    }
  };

  const closePdfPreview = () => {
    setPreviewPage(null);
    setPreviewError(null);
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    setPreviewText(null);
  };

  const handleDownload = async () => {
    if (!doc || downloading) return;
    setDownloading(true);
    try {
      const response = (await fetchWithAuth(`/documents/${doc.document_id}/download`, {
        timeoutMs: 60_000,
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
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
      await averqelAlert(
        error instanceof Error ? error.message : "Unable to download the original file.",
      );
    } finally {
      setDownloading(false);
    }
  };

  const pdfPreviewOverlay =
    previewPage !== null && typeof document !== "undefined"
      ? createPortal(
          <div
            className="fixed inset-0 z-[10000] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-md"
            role="dialog"
            aria-label={`${doc?.content_type === "application/pdf" ? "PDF" : "Document"} page ${previewPage} preview`}
          >
            <div className="bg-background border-primary/25 w-full max-w-5xl overflow-hidden rounded-2xl border p-3 shadow-2xl">
              <div className="flex items-center justify-between gap-3 pb-3">
                <p className="text-foreground text-xs font-bold tracking-widest uppercase">
                  Page {previewPage}
                </p>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setPreviewScale((value) => Math.max(0.5, value - 0.25))}
                    className="theme-pill rounded-xl p-2"
                    aria-label="Zoom out"
                  >
                    <ZoomOut size={15} />
                  </button>
                  <span className="text-muted-foreground min-w-12 text-center text-xs">
                    {Math.round(previewScale * 100)}%
                  </span>
                  <button
                    type="button"
                    onClick={() => setPreviewScale((value) => Math.min(2.5, value + 0.25))}
                    className="theme-pill rounded-xl p-2"
                    aria-label="Zoom in"
                  >
                    <ZoomIn size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={closePdfPreview}
                    className="theme-pill rounded-xl p-2"
                    aria-label="Close preview"
                  >
                    <X size={15} />
                  </button>
                </div>
              </div>
              <div className="flex max-h-[82vh] min-h-48 items-center justify-center overflow-auto rounded-xl bg-black/10 p-4 text-center">
                {previewLoading ? (
                  <AverQelLoading
                    label="Loading document preview…"
                    size="section"
                    className="w-full"
                  />
                ) : previewError ? (
                  <div className="flex flex-col items-center gap-4">
                    <p className="text-danger max-w-md text-sm font-bold">{previewError}</p>
                    <button
                      type="button"
                      onClick={() => void handleDownload()}
                      className="bg-primary text-primary-foreground inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold"
                    >
                      <Download size={14} /> Download original file
                    </button>
                  </div>
                ) : previewUrl ? (
                  <img
                    src={previewUrl}
                    alt={`Document page ${previewPage}`}
                    style={{
                      transform: `scale(${previewScale})`,
                      transformOrigin: "center center",
                    }}
                    className="mx-auto max-w-full rounded-lg shadow-lg transition-transform"
                  />
                ) : previewText !== null ? (
                  <pre
                    style={{ transform: `scale(${previewScale})`, transformOrigin: "top center" }}
                    className="theme-code-surface min-h-64 w-full max-w-4xl overflow-auto rounded-lg p-5 text-left text-xs leading-6 whitespace-pre-wrap shadow-lg transition-transform"
                  >
                    {previewText}
                  </pre>
                ) : (
                  <p className="text-muted-foreground text-sm">Preview unavailable.</p>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )
      : null;

  const addComment = async () => {
    if (!id || !commentDraft.trim()) return;
    setCommentBusy(true);
    try {
      const response = (await fetchWithAuth(`/documents/${id}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: commentDraft.trim(),
          mentions: extractMentionIds(commentDraft.trim()),
        }),
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      if (!response.ok) throw new Error("Unable to save comment.");
      const created = (await response.json()) as DocumentComment;
      setComments((current) => [...current, created]);
      setCommentDraft("");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to save comment.");
    } finally {
      setCommentBusy(false);
    }
  };

  const createShareLink = async () => {
    if (!id) return;
    setShareBusy(true);
    try {
      const response = (await fetchWithAuth(`/documents/${id}/share-links`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expires_in_seconds: 86_400 }),
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      if (!response.ok) throw new Error("Unable to create share link.");
      const data = (await response.json()) as { id?: string; share_token?: string };
      setShareLink(data.id && data.share_token ? { id: data.id, token: data.share_token } : null);
      toast.success("Share link created for 24 hours.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to create share link.");
    } finally {
      setShareBusy(false);
    }
  };

  const updateComment = async (comment: DocumentComment) => {
    const content = (await averqelPrompt("Edit comment", comment.content))?.trim();
    if (!id || !content || content === comment.content) return;
    const response = (await fetchWithAuth(`/documents/comments/${comment.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, mentions: extractMentionIds(content) }),
      silentTimeout: true,
      suppressErrorToast: true,
    })) as Response;
    if (!response.ok) {
      toast.error("Unable to edit comment.");
      return;
    }
    const updated = (await response.json()) as DocumentComment;
    setComments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  };

  const deleteComment = async (commentId: string) => {
    if (!(await averqelConfirm("Delete this comment? This cannot be undone."))) return;
    const response = (await fetchWithAuth(`/documents/comments/${commentId}`, {
      method: "DELETE",
      silentTimeout: true,
      suppressErrorToast: true,
    })) as Response;
    if (!response.ok) {
      toast.error("Unable to delete comment.");
      return;
    }
    setComments((current) => current.filter((item) => item.id !== commentId));
  };

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
      toast.error(err instanceof Error ? err.message : "Failed to send to notes.");
    }
  };

  const handleResume = async () => {
    if (!id || resuming) return;
    setResuming(true);
    try {
      const response = (await fetchWithAuth(`/documents/${id}/resume`, {
        method: "POST",
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.message || "Unable to resume ingestion.");
      toast.success("Ingestion resumed from the last committed checkpoint.");
      await fetchData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to resume ingestion.");
    } finally {
      setResuming(false);
    }
  };

  const compareVersion = async (versionId: string) => {
    if (!id || versionId === id) return;
    const response = (await fetchWithAuth(
      `/documents/${id}/versions/diff?compare_to=${versionId}`,
      { silentTimeout: true, suppressErrorToast: true },
    )) as Response;
    if (!response.ok) {
      toast.error("Unable to compare document versions.");
      return;
    }
    setVersionDiff((await response.json()) as VersionDiffResponse);
  };

  const restoreVersion = async (versionId: string) => {
    if (!id || restoringVersion) return;
    setRestoringVersion(versionId);
    try {
      const response = (await fetchWithAuth(`/documents/${id}/versions/${versionId}/restore`, {
        method: "POST",
        silentTimeout: true,
        suppressErrorToast: true,
      })) as Response;
      if (!response.ok) throw new Error("Unable to restore this version.");
      toast.success("Version restored and queued for indexing.");
      await fetchData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to restore version.");
    } finally {
      setRestoringVersion(null);
    }
  };

  useEffect(() => {
    if (!id) return;
    queueMicrotask(() => void fetchData());
  }, [fetchData, id]);

  useRealtimeEvents(
    (event) => {
      if (!id || event.data?.document_id !== id) return;
      if (getDocumentStatusPollingInterval(status) === null) return;
      if (realtimeStatusRefreshTimerRef.current !== null) return;
      const delayMs = getRealtimeStatusRefreshDelay(
        Date.now(),
        lastRealtimeStatusRefreshAtRef.current,
      );
      realtimeStatusRefreshTimerRef.current = window.setTimeout(() => {
        realtimeStatusRefreshTimerRef.current = null;
        lastRealtimeStatusRefreshAtRef.current = Date.now();
        void refreshDocumentStatus();
      }, delayMs);
    },
    ["documents"],
  );

  useEffect(
    () => () => {
      if (realtimeStatusRefreshTimerRef.current !== null) {
        window.clearTimeout(realtimeStatusRefreshTimerRef.current);
        realtimeStatusRefreshTimerRef.current = null;
      }
    },
    [id],
  );

  const pollingStatus = status?.status ?? doc?.status;
  const pollingIngestionStatus = status?.ingestion_status;
  const pollingRecoveryAvailable = status?.recovery_available;

  // Realtime events are the fast path. This single-endpoint reconciliation
  // updates progress without reloading comments, versions, and full text.
  useEffect(() => {
    if (!id) return;
    const currentStatus = pollingStatus
      ? {
          status: pollingStatus,
          ingestion_status: pollingIngestionStatus,
          recovery_available: pollingRecoveryAvailable,
        }
      : null;
    const initialDelay = getDocumentStatusPollingInterval(currentStatus);
    if (initialDelay === null) return;

    let active = true;
    let timerId: number | null = null;
    let nextDelay: number = initialDelay;
    const poll = async () => {
      const result = await refreshDocumentStatus();
      if (!active) return;

      if (result?.status) {
        const pollInterval = getDocumentStatusPollingInterval(result.status);
        if (pollInterval === null) return;
        nextDelay = pollInterval;
      } else {
        nextDelay = getDocumentStatusRetryDelay(result?.response ?? null, nextDelay);
      }

      timerId = window.setTimeout(() => void poll(), nextDelay);
    };

    timerId = window.setTimeout(() => void poll(), nextDelay);
    return () => {
      active = false;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [id, pollingIngestionStatus, pollingRecoveryAvailable, pollingStatus, refreshDocumentStatus]);

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
        <p className="text-foreground text-xl font-bold">
          {detailLoadError?.includes("not found")
            ? "Document Not Found"
            : "Could Not Load Document"}
        </p>
        <p className="text-muted-foreground max-w-md text-center text-sm" role="alert">
          {detailLoadError ?? "Document details are temporarily unavailable."}
        </p>
        <div className="flex items-center gap-4">
          {!detailLoadError?.includes("not found") ? (
            <button
              type="button"
              onClick={() => void fetchData()}
              disabled={requestRetrySeconds > 0}
              className="border-primary/25 text-primary rounded-lg border px-4 py-2 text-sm font-semibold"
            >
              {requestRetrySeconds > 0 ? `Retry in ${requestRetrySeconds}s` : "Retry"}
            </button>
          ) : null}
          <Link
            href="/dashboard/documents"
            prefetch={false}
            className="text-primary hover:underline"
          >
            Return to list
          </Link>
        </div>
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
  const readerTextIsReady =
    !status?.recovery_available && ["indexed", "completed"].includes(status?.status ?? doc.status);
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
    <div className="documents-theme-scope space-y-8 pb-12">
      {pdfPreviewOverlay}
      <Link
        href="/dashboard/documents"
        prefetch={false}
        className="hover:text-foreground group mb-4 inline-flex items-center gap-2 text-slate-700 transition-colors dark:text-slate-400"
      >
        <ArrowLeft size={18} className="transition-transform group-hover:-translate-x-1" />
        <span className="text-sm font-semibold">Back to Documents</span>
      </Link>

      {detailLoadError ? (
        <div
          className="text-foreground flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4 text-sm"
          role="status"
          aria-live="polite"
        >
          <span>{detailLoadError}</span>
          <button
            type="button"
            onClick={() => void fetchData()}
            disabled={requestRetrySeconds > 0}
            className="border-primary/25 text-primary rounded-lg border px-3 py-1.5 text-xs font-semibold disabled:cursor-wait disabled:opacity-60"
          >
            {requestRetrySeconds > 0 ? `Retry in ${requestRetrySeconds}s` : "Retry details"}
          </button>
        </div>
      ) : null}

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
                <div className="absolute top-[21px] left-0 z-0 h-1.5 w-full rounded-sm bg-slate-200 dark:bg-slate-800/80" />

                {/* Active Progress Track */}
                <div
                  className="absolute top-[21px] left-0 z-0 h-1.5 rounded-sm bg-gradient-to-r from-teal-500 to-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.45)] transition-all duration-1000"
                  style={{
                    width: `${Math.max(0, (boundedStepIndex / (steps.length - 1)) * 100)}%`,
                  }}
                />

                {steps.map((step, idx) => {
                  const isCompleted = idx < boundedStepIndex || normalizedStatus === "indexed";
                  const isActive =
                    idx === boundedStepIndex && normalizedStatus !== "indexed" && !isFailed;

                  return (
                    <button
                      key={step.id}
                      type="button"
                      onClick={() =>
                        step.id === "security" && setShowSecurityVerification((open) => !open)
                      }
                      className={`group relative z-10 flex flex-col items-center ${step.id === "security" ? "cursor-pointer" : "cursor-default"}`}
                      aria-expanded={step.id === "security" ? showSecurityVerification : undefined}
                    >
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
                    </button>
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
                <div className="relative h-3 overflow-hidden rounded-sm bg-slate-200/60 p-[2px] shadow-inner dark:bg-slate-800/80">
                  <div
                    className="relative h-full overflow-hidden rounded-sm bg-gradient-to-r from-teal-500 via-emerald-400 to-emerald-500 transition-all duration-700"
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

              {showSecurityVerification ? (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-5 rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.05] p-5"
                >
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <p className="flex items-center gap-2 text-[10px] font-black tracking-[0.2em] text-emerald-800 uppercase dark:text-emerald-300">
                      <ShieldCheck size={15} /> Security verification
                    </p>
                    <span className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[9px] font-black tracking-wider text-emerald-700 uppercase dark:text-emerald-300">
                      {status?.security_scan_result === "passed" ? "Passed" : "Record unavailable"}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-3">
                    <div>
                      <p className="text-foreground/45 text-[9px] font-black tracking-wider uppercase">
                        Document scan
                      </p>
                      <p className="text-foreground mt-1 font-bold">
                        {status?.security_scan_result === "passed"
                          ? "Malware scan passed"
                          : "No persisted receipt"}
                      </p>
                    </div>
                    <div>
                      <p className="text-foreground/45 text-[9px] font-black tracking-wider uppercase">
                        Verified at
                      </p>
                      <p className="text-foreground mt-1 font-bold">
                        {status?.security_scanned_at
                          ? new Date(status.security_scanned_at).toLocaleString()
                          : "Not recorded"}
                      </p>
                    </div>
                    <div>
                      <p className="text-foreground/45 text-[9px] font-black tracking-wider uppercase">
                        Enforcement
                      </p>
                      <p className="text-foreground mt-1 font-bold">
                        {status?.security_scan_required
                          ? "Required / fail closed"
                          : "Configured policy"}
                      </p>
                    </div>
                  </div>
                  <p className="text-foreground/55 mt-4 text-[10px] leading-relaxed">
                    Every accepted upload passes the security gate before private storage and
                    indexing. Existing files without a stored receipt are not retroactively labelled
                    verified.
                  </p>
                </motion.div>
              ) : null}

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

              {status?.recovery_available && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-5 rounded-2xl border border-amber-500/25 bg-amber-500/[0.06] p-5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p className="flex items-center gap-2 text-sm font-black text-amber-800 dark:text-amber-300">
                        <Clock size={16} /> Checkpoint recovery available
                      </p>
                      <p className="text-foreground/60 mt-1 text-xs">
                        {status.recovery_reason} {status.embedded_chunk_count} of{" "}
                        {status.total_chunk_count} chunks committed; {status.remaining_chunk_count}{" "}
                        remain.
                      </p>
                      {status.last_checkpoint_at && (
                        <p className="text-foreground/45 mt-2 text-[10px] font-bold tracking-wide uppercase">
                          Last checkpoint {new Date(status.last_checkpoint_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={handleResume}
                      disabled={resuming}
                      className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-xs font-black text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {resuming ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <RotateCcw size={15} />
                      )}
                      {resuming ? "Resuming..." : "Resume from checkpoint"}
                    </button>
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
                <div className="flex items-center gap-3">
                  {doc.extraction_ocr_used ? (
                    <span className="border-primary/25 bg-primary/10 text-primary rounded-md border px-2 py-1 text-[9px] font-black tracking-wider uppercase">
                      OCR extracted
                    </span>
                  ) : null}
                  <div className="text-foreground/30 text-[10px] font-bold tracking-wider uppercase">
                    {viewMode === "reader"
                      ? fullTextLoading
                        ? "Loading text"
                        : fullText?.length
                          ? `${Math.ceil(fullText.length / 5)} words`
                          : fullTextError || fullTextLoadedFor === id
                            ? "Text unavailable"
                            : readerTextIsReady
                              ? "Text ready"
                              : "Processing"
                      : `${chunks.length} fragments`}
                  </div>
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
                        <AverQelLoading label="Loading document text…" size="compact" />
                      ) : fullTextError ? (
                        <div className="border-danger/25 bg-danger/5 flex max-w-lg flex-col items-center gap-3 rounded-xl border p-5 text-center">
                          <AlertCircle size={24} className="text-danger" />
                          <p className="text-foreground text-sm" role="alert">
                            {fullTextError}
                          </p>
                          <button
                            type="button"
                            onClick={() => void loadFullText()}
                            disabled={fullTextLoading || requestRetrySeconds > 0}
                            className="border-primary/25 text-primary rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-wait disabled:opacity-60"
                          >
                            {requestRetrySeconds > 0
                              ? `Retry in ${requestRetrySeconds}s`
                              : "Retry text loading"}
                          </button>
                        </div>
                      ) : readerTextIsReady && fullTextLoadedFor === id ? (
                        <>
                          <AlertCircle size={32} className="text-foreground/20" />
                          <p className="text-foreground/50 text-center text-sm">
                            No extracted text is available for this document.
                          </p>
                        </>
                      ) : readerTextIsReady ? (
                        <>
                          <FileText size={28} className="text-foreground/30" />
                          <p className="text-foreground/50 text-center text-sm">
                            Reader text is ready to load.
                          </p>
                          <button
                            type="button"
                            onClick={() => void loadFullText()}
                            disabled={fullTextLoading || requestRetrySeconds > 0}
                            className="border-primary/25 text-primary rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-wait disabled:opacity-60"
                          >
                            {requestRetrySeconds > 0
                              ? `Retry in ${requestRetrySeconds}s`
                              : "Load extracted text"}
                          </button>
                        </>
                      ) : (
                        <>
                          <Clock size={24} className="text-foreground/30" />
                          <p className="text-foreground/50 text-center text-sm">
                            Extracted text will be loaded after document processing finishes.
                          </p>
                        </>
                      )}
                    </div>
                  )
                ) : (
                  <div className="space-y-6">
                    {chunksError ? (
                      <div
                        className="border-danger/25 bg-danger/5 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4 text-sm"
                        role="alert"
                      >
                        <span>{chunksError}</span>
                        <button
                          type="button"
                          onClick={() => void fetchChunks(0, false)}
                          disabled={requestRetrySeconds > 0}
                          className="border-primary/25 text-primary rounded-lg border px-3 py-2 text-xs font-semibold disabled:cursor-wait disabled:opacity-60"
                        >
                          {requestRetrySeconds > 0
                            ? `Retry in ${requestRetrySeconds}s`
                            : "Retry fragments"}
                        </button>
                      </div>
                    ) : null}
                    {chunks.length > 0 ? (
                      chunks.map((chunk) => (
                        <div
                          key={chunk.chunk_index}
                          id={`fragment-${chunk.chunk_index}`}
                          className="border-primary/30 relative border-l pl-6"
                        >
                          <div className="bg-primary absolute top-0 left-[-5px] h-2.5 w-2.5 rounded-full shadow-[0_0_8px_rgba(var(--primary),0.5)]" />
                          <div className="mb-3 flex items-center justify-between">
                            <div className="flex min-w-0 items-center gap-2">
                              <p className="text-primary text-[10px] font-bold tracking-[0.2em] uppercase">
                                Fragment {chunk.chunk_index + 1}
                              </p>
                              {typeof chunk.metadata?.mode === "string" ? (
                                <span className="text-foreground/55 bg-foreground/[0.05] rounded px-1.5 py-0.5 text-[8px] font-black tracking-wider uppercase">
                                  {chunk.metadata.mode}
                                </span>
                              ) : null}
                              {typeof chunk.metadata?.page_number === "number" ? (
                                <span className="text-foreground/45 text-[9px] font-bold tabular-nums">
                                  Page {chunk.metadata.page_number}
                                </span>
                              ) : null}
                            </div>
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
                        className="bg-primary text-primary-foreground flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-black tracking-widest uppercase shadow-2xl transition-all hover:scale-105 active:scale-95"
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
                    className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/15 inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-xs font-bold tracking-[0.2em] uppercase transition disabled:cursor-not-allowed disabled:opacity-60"
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
          {canViewClassificationHistory ? (
            <div className="glass-card space-y-6 p-6">
              <h3 className="text-foreground border-glass-border/60 flex items-center gap-2 border-b pb-4 text-sm font-bold tracking-widest uppercase">
                <Tag size={16} className="text-primary" /> Classification history
              </h3>
              {classificationHistory.length ? (
                <div className="space-y-2">
                  {classificationHistory.map((item) => (
                    <div key={item.id} className="theme-chip rounded-xl p-3 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold">{item.rule_name}</span>
                        <span className="text-muted-foreground text-[10px]">
                          {item.source} · {item.status}
                        </span>
                      </div>
                      <p className="text-muted-foreground mt-1 text-[10px]">
                        {Object.entries(item.actions)
                          .filter(([, changed]) => changed)
                          .map(([action]) => action.replaceAll("_", " "))
                          .join(" · ") || "Matched; no new assignment was needed"}
                      </p>
                      {item.error_message ? (
                        <p className="text-danger mt-1 text-[10px]">{item.error_message}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-foreground/50 text-xs">
                  No classification rules have matched this document.
                </p>
              )}
            </div>
          ) : null}

          <div className="glass-card space-y-6 p-6">
            <h3 className="text-foreground border-glass-border/60 flex items-center gap-2 border-b pb-4 text-sm font-bold tracking-widest uppercase">
              <Brain size={16} className="text-primary" /> Document actions
            </h3>
            <div className="flex flex-wrap gap-2">
              <div className="relative z-20">
                <button
                  ref={aiActionButtonRef}
                  type="button"
                  aria-haspopup="listbox"
                  aria-expanded={aiActionMenuOpen}
                  onClick={() => setAiActionMenuOpen((open) => !open)}
                  className="theme-input flex min-w-40 items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-xs"
                >
                  <span>
                    {
                      {
                        summarize: "Summarize",
                        extract: "Extract facts",
                        faqs: "Generate FAQs",
                        compare: "Compare versions",
                      }[aiAction]
                    }
                  </span>
                  <ChevronRight
                    size={14}
                    className={`transition-transform ${aiActionMenuOpen ? "rotate-90" : ""}`}
                  />
                </button>
                {aiActionMenuOpen ? (
                  <div
                    role="listbox"
                    aria-label="Document action"
                    className="border-glass-border bg-background absolute top-[calc(100%+0.4rem)] left-0 z-50 min-w-full overflow-hidden rounded-xl border p-1 shadow-2xl"
                  >
                    {(["summarize", "extract", "faqs", "compare"] as const).map((action) => (
                      <button
                        key={action}
                        type="button"
                        role="option"
                        aria-selected={aiAction === action}
                        onClick={() => {
                          setAiAction(action);
                          setAiActionMenuOpen(false);
                        }}
                        className={`block w-full rounded-lg px-3 py-2 text-left text-xs font-bold ${aiAction === action ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-primary/10"}`}
                      >
                        {
                          {
                            summarize: "Summarize",
                            extract: "Extract facts",
                            faqs: "Generate FAQs",
                            compare: "Compare versions",
                          }[action]
                        }
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => void runAiAction()}
                disabled={aiBusy}
                className="bg-primary text-primary-foreground rounded-xl px-4 py-2 text-xs font-bold transition hover:brightness-110 disabled:opacity-50"
              >
                {aiBusy ? "Working..." : "Run grounded action"}
              </button>
            </div>
            {aiAnswer ? (
              <>
                <pre className="theme-code-surface max-h-52 overflow-auto rounded-xl p-3 text-xs leading-relaxed whitespace-pre-wrap">
                  {aiAnswer}
                </pre>
                {aiCitations.length ? (
                  <div className="flex flex-wrap gap-2">
                    {aiCitations.map((citation, index) => (
                      <button
                        key={`${String(citation.chunk_id ?? citation.id ?? index)}`}
                        type="button"
                        onClick={() => {
                          const page = Number(citation.page_number ?? citation.page ?? 0);
                          const chunk = Number(citation.chunk_index ?? -1);
                          if (page > 0) {
                            setPreviewPage(page);
                            setPreviewScale(1);
                          } else if (chunk >= 0)
                            document
                              .getElementById(`fragment-${chunk}`)
                              ?.scrollIntoView({ behavior: "smooth", block: "center" });
                        }}
                        className="theme-pill px-2.5 py-1.5 text-[10px] font-bold"
                      >
                        Source {index + 1}
                        {citation.page_number ? ` · p.${citation.page_number}` : ""}
                      </button>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-foreground/50 text-xs">
                Actions use indexed document content and return grounded citations through the
                existing query pipeline.
              </p>
            )}
          </div>

          <div className="glass-card space-y-6 p-6">
            <h3 className="text-foreground border-glass-border/60 flex items-center gap-2 border-b pb-4 text-sm font-bold tracking-widest uppercase">
              <Database size={16} className="text-primary" /> Quality diagnostics
            </h3>
            <div className="grid grid-cols-2 gap-3 text-xs xl:grid-cols-4">
              <div className="theme-chip min-w-0 rounded-xl p-4">
                <p className="text-foreground/55 truncate text-[9px] font-black tracking-wider uppercase">
                  Coverage
                </p>
                <p className="text-foreground mt-1 text-sm font-black whitespace-nowrap">
                  {quality?.extraction_coverage_score == null
                    ? "Not measured"
                    : `${Math.round(quality.extraction_coverage_score * 100)}%`}
                </p>
              </div>
              <div className="theme-chip min-w-0 rounded-xl p-4">
                <p className="text-foreground/55 truncate text-[9px] font-black tracking-wider uppercase">
                  Chunks
                </p>
                <p className="text-foreground mt-1 text-sm font-black whitespace-nowrap">
                  {quality?.total_chunks ?? "—"}
                </p>
              </div>
              <div className="theme-chip min-w-0 rounded-xl p-4">
                <p className="text-foreground/55 truncate text-[9px] font-black tracking-wider uppercase">
                  OCR
                </p>
                <p className="text-foreground mt-1 text-sm font-black whitespace-nowrap">
                  {quality?.ocr_used ? "Used" : "Not used"}
                </p>
              </div>
              <div className="theme-chip min-w-0 rounded-xl p-4">
                <p className="text-foreground/55 truncate text-[9px] font-black tracking-wider uppercase">
                  Page gaps
                </p>
                <p className="text-foreground mt-1 text-sm font-black whitespace-nowrap">
                  {quality?.missing_page_numbers.length ?? 0}
                </p>
              </div>
            </div>
            {quality?.warnings.length ? (
              <p className="rounded-xl border border-amber-300/50 bg-amber-50/70 p-3 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
                {quality.warnings.join(" · ")}
              </p>
            ) : null}
            {Object.keys(thumbnailUrls).length ? (
              <div className="overflow-x-auto">
                <div className="flex gap-3 pb-2">
                  {Object.entries(thumbnailUrls).map(([page, url]) => (
                    <button
                      key={page}
                      type="button"
                      onClick={() => {
                        setPreviewPage(Number(page));
                        setPreviewScale(1);
                      }}
                      className="group shrink-0"
                    >
                      <img
                        src={url}
                        alt={`Page ${page} thumbnail`}
                        className="border-primary/15 group-hover:border-primary h-24 w-16 rounded-lg border object-cover transition group-hover:shadow-lg"
                      />
                      <span className="text-foreground/50 mt-1 block text-center text-[9px] font-bold">
                        Page {page}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {previewPage !== null ? (
              <div
                className="border-glass-border bg-background/80 fixed inset-0 z-50 flex items-center justify-center border p-4 backdrop-blur-md"
                role="dialog"
                aria-label={`PDF page ${previewPage} preview`}
              >
                <div className="theme-panel relative flex max-h-[95vh] max-w-5xl flex-col overflow-hidden rounded-2xl p-3 shadow-2xl">
                  <div className="flex items-center justify-between gap-3 pb-3">
                    <p className="text-foreground text-xs font-bold tracking-widest uppercase">
                      Page {previewPage}
                    </p>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setPreviewScale((value) => Math.max(0.5, value - 0.25))}
                        className="theme-pill p-2"
                        aria-label="Zoom out"
                      >
                        <ZoomOut size={15} />
                      </button>
                      <span className="text-muted-foreground min-w-12 text-center text-xs">
                        {Math.round(previewScale * 100)}%
                      </span>
                      <button
                        type="button"
                        onClick={() => setPreviewScale((value) => Math.min(2.5, value + 0.25))}
                        className="theme-pill p-2"
                        aria-label="Zoom in"
                      >
                        <ZoomIn size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setPreviewPage(null)}
                        className="theme-pill p-2"
                        aria-label="Close preview"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[82vh] overflow-auto rounded-xl bg-black/10 p-3 text-center">
                    <img
                      src={thumbnailUrls[previewPage]}
                      alt={`PDF page ${previewPage}`}
                      style={{ transform: `scale(${previewScale})`, transformOrigin: "top center" }}
                      className="mx-auto max-w-none rounded-lg shadow-lg transition-transform"
                    />
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          <div className="glass-card space-y-6 p-6">
            <h3 className="text-foreground border-glass-border/60 flex items-center gap-2 border-b pb-4 text-sm font-bold tracking-widest uppercase">
              <MessageSquare size={16} className="text-primary" /> Comments
            </h3>
            <div className="space-y-3">
              {comments.map((comment) => (
                <div key={comment.id} className="theme-chip flex items-start gap-3 rounded-xl p-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground/80 text-xs">{comment.content}</p>
                    <p className="text-foreground/40 mt-1 text-[10px]">
                      {new Date(comment.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => void updateComment(comment)}
                      title="Edit comment"
                      className="text-foreground/40 hover:bg-primary/10 hover:text-primary rounded-lg p-1.5 transition"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteComment(comment.id)}
                      title="Delete comment"
                      className="text-foreground/40 rounded-lg p-1.5 transition hover:bg-red-500/10 hover:text-red-500"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
              {!comments.length ? (
                <p className="text-foreground/50 text-xs">No comments yet.</p>
              ) : null}
              <div className="flex gap-2">
                <input
                  value={commentDraft}
                  onChange={(event) => setCommentDraft(event.target.value)}
                  placeholder="Comment — mention a tenant user with @user-id"
                  className="theme-input min-w-0 flex-1 rounded-xl px-3 py-2 text-xs"
                  maxLength={5000}
                />
                <button
                  type="button"
                  onClick={() => void addComment()}
                  disabled={commentBusy || !commentDraft.trim()}
                  className="bg-primary text-primary-foreground rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50"
                >
                  {commentBusy ? "Saving" : "Post"}
                </button>
              </div>
            </div>
          </div>

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
                        className="block min-w-0 font-mono text-xs break-all whitespace-normal text-[#78350f] dark:text-amber-200"
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
            <div className="border-primary/15 bg-primary/[0.03] rounded-xl border p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="flex items-center gap-2 text-xs font-bold">
                  <Link2 size={14} className="text-primary" /> Secure share link
                </p>
                <button
                  type="button"
                  onClick={() => void createShareLink()}
                  disabled={shareBusy}
                  className="bg-primary text-primary-foreground rounded-lg px-3 py-2 text-[10px] font-bold disabled:opacity-50"
                >
                  {shareBusy ? "Creating..." : "Create 24h link"}
                </button>
              </div>
              {shareLink ? (
                <div className="mt-3 flex gap-2">
                  <code className="theme-code-surface min-w-0 flex-1 truncate rounded-lg p-2 text-[10px]">{`${window.location.origin}/share/${shareLink.id}?token=${encodeURIComponent(shareLink.token)}`}</code>
                  <button
                    type="button"
                    onClick={() =>
                      void navigator.clipboard?.writeText(
                        `${window.location.origin}/share/${shareLink.id}?token=${encodeURIComponent(shareLink.token)}`,
                      )
                    }
                    className="border-primary/20 text-primary rounded-lg border px-3 text-[10px] font-bold"
                  >
                    Copy
                  </button>
                </div>
              ) : null}
            </div>
            <div className="space-y-4">
              {versions.length > 1 ? (
                <div className="space-y-3">
                  {versions.map((v) => (
                    <div
                      key={v.document_id}
                      className={`flex items-center gap-2 rounded-xl border p-3 transition-all ${v.document_id === id ? "border-primary/30 bg-primary/10 text-primary" : "theme-chip text-slate-700 dark:text-slate-400"}`}
                    >
                      <Link
                        href={`/dashboard/documents/${v.document_id}`}
                        prefetch={false}
                        className="flex min-w-0 flex-1 items-center gap-3"
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={`h-2 w-2 rounded-full ${v.status === "indexed" ? "bg-green-500" : "bg-yellow-500"}`}
                          />
                          <div>
                            <p className="text-xs font-bold tracking-wider uppercase">
                              v{v.version}
                            </p>
                            <p className="font-mono text-[10px] opacity-60">
                              {new Date(v.created_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                        <ChevronRight size={14} />
                      </Link>
                      {v.document_id !== id && (
                        <>
                          <button
                            type="button"
                            onClick={() => void compareVersion(v.document_id)}
                            title="Compare version"
                            className="text-foreground/50 hover:bg-primary/10 hover:text-primary rounded-lg p-2 transition"
                          >
                            <GitCompare size={14} />
                          </button>
                          <button
                            type="button"
                            onClick={() => void restoreVersion(v.document_id)}
                            disabled={restoringVersion === v.document_id}
                            title="Restore version"
                            className="text-foreground/50 rounded-lg p-2 transition hover:bg-emerald-500/10 hover:text-emerald-600 disabled:opacity-50"
                          >
                            <RotateCcw
                              size={14}
                              className={restoringVersion === v.document_id ? "animate-spin" : ""}
                            />
                          </button>
                        </>
                      )}
                    </div>
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
              {versionDiff && (
                <div className="border-primary/20 bg-primary/[0.04] mt-4 rounded-xl border p-4">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <p className="text-xs font-black tracking-wider uppercase">
                      v{versionDiff.from_version} → v{versionDiff.to_version}
                    </p>
                    <button
                      type="button"
                      onClick={() => setVersionDiff(null)}
                      className="text-foreground/50 hover:text-primary text-xs"
                    >
                      Close
                    </button>
                  </div>
                  <pre className="text-foreground/70 max-h-64 overflow-auto text-[10px] leading-relaxed whitespace-pre-wrap">
                    {versionDiff.changed
                      ? versionDiff.unified_diff ||
                        "Content changed, but no line diff was generated."
                      : "No content changes."}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
