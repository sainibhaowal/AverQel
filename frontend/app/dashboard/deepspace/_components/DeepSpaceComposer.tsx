"use client";

/* Local object URLs are short-lived, private composer previews; Next image optimization cannot fetch them. */
/* eslint-disable @next/next/no-img-element */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { createPortal } from "react-dom";
import {
  Bot,
  ChevronDown,
  Check,
  CircleHelp,
  Gauge,
  Mic,
  MicOff,
  Play,
  Square,
  Trash2,
  Paperclip,
  X,
  FileText,
  Camera,
  RotateCw,
  FolderOpen,
  Pencil,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { fetchWithAuth } from "@/lib/api";
import ProviderLogo from "@/app/components/providers/ProviderLogo";
import type { DeepSpaceMessageAttachment } from "../_lib/deepspace-stream";
import { formatReasoningEffortLabel, isValidReasoningEffort } from "../_lib/reasoning-options";
import type { TaskProgress } from "../_lib/task-progress";
import DeepSpaceTaskPlanDrawer from "./DeepSpaceTaskPlanDrawer";
import DeepSpaceLiveOutputRate from "./DeepSpaceLiveOutputRate";
import DeepSpaceVoicePresence from "./DeepSpaceVoicePresence";

type ReasoningEffort = string;

interface DeepSpaceComposerProps {
  conversationId?: string | null;
  query: string;
  isStreaming: boolean;
  showActiveResponseControls?: boolean;
  stopping?: boolean;
  taskProgress?: TaskProgress | null;
  onQueryChange: (value: string) => void;
  onSubmit: (attachments?: DeepSpaceMessageAttachment[]) => void;
  editingQueuedTurnId?: string | null;
  onEditQueuedTurn?: (clientRequestId: string) => void;
  onCancelQueueEdit?: () => void;
  onSaveQueueEdit?: (clientRequestId: string, message: string) => Promise<boolean>;
  onStop: () => void;
  onSteer?: () => void;
  queuedTurns?: Array<{
    clientRequestId: string;
    regenerateMessageId?: string | null;
    prompt: string;
    status: string;
    error?: string | null;
  }>;
  queuePaused?: boolean;
  queuePauseReason?: string | null;
  queueFailedRequestId?: string | null;
  queueAction?: string | null;
  onPauseQueue?: () => void;
  onResumeQueue?: () => void;
  onClearQueue?: () => void;
  onCancelQueuedTurn?: (clientRequestId: string) => void;
  onRetryFailedTurn?: (clientRequestId: string) => void;
  onSteerQueuedTurn?: (clientRequestId: string) => void;
  changedFiles?: Array<{ path: string; additions: number; deletions: number }>;
  modelName?: string | null;
  selectedProviderId?: string | null;
  reasoningEffort?: ReasoningEffort | null;
  onReasoningEffortChange?: (value: ReasoningEffort | null) => void;
  availableModels?: Array<{
    providerId: string;
    providerName?: string;
    providerType?: string;
    modelName: string;
    displayName: string;
    quantization?: string | null;
    contextWindow?: number | null;
    contextWindowSource?: string | null;
    supportedReasoningEfforts?: string[];
    reasoningCapabilitiesKnown?: boolean;
    reasoningToggleOnly?: boolean;
    reasoningAlwaysOn?: boolean;
    defaultReasoningEffort?: string;
    reasoningEffortValues?: Record<string, string>;
  }>;
  onModelSelect?: (providerId: string, modelName: string) => void;
  voiceState?: "idle" | "listening" | "thinking" | "speaking";
  voiceActivityLevel?: number;
  contextUsedTokens?: number | null;
  contextLimit?: number | null;
  contextRemainingTokens?: number | null;
  safeRemainingTokens?: number | null;
  sessionInputTokens?: number | null;
  sessionOutputTokens?: number | null;
  sessionTotalTokens?: number | null;
  requestInputTokens?: number | null;
  requestOutputTokens?: number | null;
  requestInputTokensSource?: string | null;
  requestOutputTokensSource?: string | null;
  liveOutputTokens?: number;
  liveOutputStartedAtMs?: number | null;
  reservedOutputTokens?: number | null;
  maxOutputTokens?: number | null;
  contextStatus?: string | null;
  contextCompacted?: boolean;
  contextEpoch?: number | null;
  contextEpochReason?: string | null;
  contextSourceUpdates?: string[];
  userVisibleInputTokens?: number | null;
  userVisibleOutputTokens?: number | null;
  conversationVisibleTokens?: number | null;
  promptCacheMode?: string | null;
  promptCacheEligible?: boolean;
  promptCacheStatus?: string | null;
  systemContextTokens?: number | null;
  toolSchemaTokens?: number | null;
  toolResultTokens?: number | null;
  adaptiveHistoryBudgetTokens?: number | null;
  adaptiveToolResultBudgetTokens?: number | null;
  uncachedInputTokens?: number | null;
  providerUsage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    cached_input_tokens?: number | null;
    cache_write_input_tokens?: number | null;
    usage_source?: string;
  } | null;
  providerUsageScope?: string | null;
  providerUsageRoundCount?: number | null;
  providerTurnUsage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    cached_input_tokens?: number | null;
    cache_write_input_tokens?: number | null;
    usage_source?: string;
  } | null;
  tokenCategorySource?: string | null;
  sttActive?: boolean;
  dictationSessionOpen?: boolean;
  dictationControlPending?: boolean;
  dictationElapsedSeconds?: number;
  ttsActive?: boolean;
  onSttToggle?: () => void;
  onDictationPause?: () => void;
  onDictationFinish?: () => void;
  onTtsToggle?: () => void;
  voiceLabel?: string;
  runtimePhase?: DeepSpaceRuntimePhase;
  activeToolName?: string | null;
  hasRuntimeError?: boolean;
}

type ComposerExtractionStatus = {
  state: "processing" | "extracted" | "no_text" | "unavailable" | "not_attempted";
  ocr_used: boolean;
};

type ComposerAttachment = {
  id: string;
  name: string;
  type: string;
  size: number;
  previewUrl?: string;
  status: "uploading" | "processing" | "ready" | "error";
  error?: string;
  loaded?: number;
  file?: File;
  uploadId?: string;
  extractionStatus?: ComposerExtractionStatus | null;
};

function attachmentExtractionLabel(
  status: ComposerExtractionStatus | null | undefined,
): string | null {
  if (!status || status.state === "not_attempted") return null;
  if (status.state === "processing") return "Uploaded · reading text";
  if (status.state === "extracted")
    return status.ocr_used ? "Text extracted · OCR used" : "Text extracted";
  if (status.state === "no_text") return "No readable text found";
  return "Text extraction unavailable";
}

type AttachmentTooltipKind = "files" | "camera" | "library";

type ActiveAttachmentTooltip = {
  kind: AttachmentTooltipKind;
  id: string;
  label: string;
  anchor: HTMLButtonElement;
  left: number;
  top: number;
};

export type DeepSpaceRuntimePhase =
  | "idle"
  | "typing"
  | "submitting"
  | "thinking"
  | "tool_calling"
  | "receiving"
  | "completed"
  | "error";

const attachmentTooltipClassName =
  "averqel-tooltip-surface pointer-events-none fixed z-[10000] max-w-[min(18rem,calc(100vw-1.5rem))] -translate-y-full rounded-xl border px-3 py-2 text-left text-[11px] leading-4 font-semibold whitespace-normal shadow-xl";

function getAttachmentTooltipPosition(anchor: HTMLButtonElement) {
  const bounds = anchor.getBoundingClientRect();
  const maxWidth = Math.min(288, Math.max(0, window.innerWidth - 24));
  const maxLeft = Math.max(12, window.innerWidth - maxWidth - 12);

  return {
    left: Math.min(Math.max(bounds.left, 12), maxLeft),
    top: Math.max(12, bounds.top - 8),
  };
}

function SendIcon() {
  return <Play className="h-[18px] w-[18px] translate-x-px fill-current" strokeWidth={2.5} />;
}

function resizeComposerTextarea(textarea: HTMLTextAreaElement) {
  const computedStyle = window.getComputedStyle(textarea);
  const px = (value: string) => Number.parseFloat(value) || 0;
  const lineHeight = px(computedStyle.lineHeight) || 24;
  const verticalPadding = px(computedStyle.paddingTop) + px(computedStyle.paddingBottom);
  const verticalBorder = px(computedStyle.borderTopWidth) + px(computedStyle.borderBottomWidth);
  const maxHeight = lineHeight * 5 + verticalPadding + verticalBorder;

  textarea.style.height = "auto";
  const contentHeight = textarea.scrollHeight + verticalBorder;
  textarea.style.height = `${Math.min(contentHeight, maxHeight)}px`;
  textarea.style.overflowY = contentHeight > maxHeight ? "auto" : "hidden";
}

function StopIcon() {
  return <Square className="h-4 w-4 fill-current" strokeWidth={2.5} />;
}

function formatDictationElapsed(seconds: number) {
  const boundedSeconds = Math.max(0, Math.min(600, Math.floor(seconds)));
  const minutes = Math.floor(boundedSeconds / 60);
  const remainingSeconds = boundedSeconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

export default function DeepSpaceComposer({
  conversationId,
  query,
  isStreaming,
  showActiveResponseControls,
  onQueryChange,
  onSubmit,
  editingQueuedTurnId = null,
  onEditQueuedTurn,
  onCancelQueueEdit,
  onSaveQueueEdit,
  onStop,
  stopping = false,
  taskProgress = null,
  onSteer,
  queuedTurns = [],
  queuePaused = false,
  queuePauseReason = null,
  queueFailedRequestId = null,
  queueAction = null,
  onPauseQueue,
  onResumeQueue,
  onClearQueue,
  onCancelQueuedTurn,
  onRetryFailedTurn,
  onSteerQueuedTurn,
  changedFiles = [],
  modelName,
  selectedProviderId = null,
  reasoningEffort = null,
  onReasoningEffortChange,
  availableModels = [],
  onModelSelect,
  voiceState = "idle",
  voiceActivityLevel = 0,
  contextUsedTokens = null,
  contextLimit = null,
  contextRemainingTokens = null,
  safeRemainingTokens = null,
  sessionTotalTokens = null,
  requestInputTokens = null,
  requestOutputTokens = null,
  requestInputTokensSource = null,
  requestOutputTokensSource = null,
  liveOutputTokens = 0,
  liveOutputStartedAtMs = null,
  reservedOutputTokens = null,
  maxOutputTokens = null,
  contextStatus = null,
  contextCompacted = false,
  contextEpoch = null,
  contextEpochReason = null,
  contextSourceUpdates = [],
  userVisibleInputTokens = null,
  userVisibleOutputTokens = null,
  conversationVisibleTokens = null,
  promptCacheMode = null,
  promptCacheEligible = false,
  promptCacheStatus = null,
  systemContextTokens = null,
  toolSchemaTokens = null,
  toolResultTokens = null,
  adaptiveHistoryBudgetTokens = null,
  adaptiveToolResultBudgetTokens = null,
  uncachedInputTokens = null,
  providerUsage = null,
  providerUsageScope = null,
  providerUsageRoundCount = null,
  providerTurnUsage = null,
  tokenCategorySource = null,
  sttActive = false,
  dictationSessionOpen = false,
  dictationControlPending = false,
  dictationElapsedSeconds = 0,
  ttsActive = false,
  onSttToggle,
  onDictationPause,
  onDictationFinish,
  onTtsToggle,
  voiceLabel = "",
  runtimePhase = "idle",
  activeToolName = null,
  hasRuntimeError = false,
}: DeepSpaceComposerProps) {
  const shouldShowActiveResponseControls = showActiveResponseControls ?? isStreaming;
  const reduceMotion = useReducedMotion();
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [modelGroupExpansion, setModelGroupExpansion] = useState<{
    search: string;
    providerId: string | null;
  } | null>(null);
  const [reasoningDropdownOpen, setReasoningDropdownOpen] = useState(false);
  const [runtimeLegendOpen, setRuntimeLegendOpen] = useState(false);
  const [contextDialogOpen, setContextDialogOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [activeAttachmentTooltip, setActiveAttachmentTooltip] =
    useState<ActiveAttachmentTooltip | null>(null);
  const priorQueueEditAttachmentsRef = useRef<ComposerAttachment[] | null>(null);
  const previousEditingQueueTurnRef = useRef<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [attachmentPreview, setAttachmentPreview] = useState<ComposerAttachment | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const uploadControllersRef = useRef<Record<string, AbortController>>({});
  const [libraryPickerOpen, setLibraryPickerOpen] = useState(false);
  const [libraryFiles, setLibraryFiles] = useState<
    Array<{
      id: string;
      name: string;
      content_type: string;
      size_bytes: number;
      extraction_status?: ComposerExtractionStatus | null;
    }>
  >([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);

  const showAttachmentTooltip = (
    kind: AttachmentTooltipKind,
    id: string,
    label: string,
    anchor: HTMLButtonElement,
  ) => {
    setActiveAttachmentTooltip({
      kind,
      id,
      label,
      anchor,
      ...getAttachmentTooltipPosition(anchor),
    });
  };

  useEffect(() => {
    const anchor = activeAttachmentTooltip?.anchor;
    if (!anchor) return;

    const reposition = () => {
      setActiveAttachmentTooltip((current) =>
        current?.anchor === anchor
          ? { ...current, ...getAttachmentTooltipPosition(anchor) }
          : current,
      );
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [activeAttachmentTooltip?.anchor]);

  useEffect(() => {
    const previousId = previousEditingQueueTurnRef.current;
    if (editingQueuedTurnId && !previousId) {
      // Preserve any unrelated composer attachments while the queued prompt
      // is in the editor. Attachments already on the queued turn stay in place.
      priorQueueEditAttachmentsRef.current = attachments;
      setAttachments([]);
    } else if (!editingQueuedTurnId && previousId) {
      setAttachments(priorQueueEditAttachmentsRef.current ?? []);
      priorQueueEditAttachmentsRef.current = null;
    }
    previousEditingQueueTurnRef.current = editingQueuedTurnId ?? null;
  }, [attachments, editingQueuedTurnId]);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) resizeComposerTextarea(textarea);
  }, [query]);

  useEffect(() => {
    if (!editingQueuedTurnId) return;
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  }, [editingQueuedTurnId]);

  const importAttachments = async (input: FileList | File[]) => {
    if (!conversationId || editingQueuedTurnId) return;
    const allFiles = Array.from(input);
    const invalid = allFiles.filter(
      (file) => !file.name || file.size <= 0 || file.size > 25 * 1024 * 1024,
    );
    if (invalid.length)
      setAttachmentError(
        "Files must have content and be 25 MB or smaller. Unsupported types are safely rejected by Library.",
      );
    const files = allFiles
      .filter((file) => file.name && file.size > 0 && file.size <= 25 * 1024 * 1024)
      .slice(0, Math.max(0, 10 - attachments.length));
    for (const file of files) {
      const localId = crypto.randomUUID();
      const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
      const controller = new AbortController();
      uploadControllersRef.current[localId] = controller;
      setAttachments((current) => [
        ...current,
        {
          id: localId,
          name: file.name,
          type: file.type,
          size: file.size,
          previewUrl,
          status: "uploading",
          loaded: 0,
          file,
        },
      ]);
      try {
        const created = (await fetchWithAuth(`/deepspace/library/${conversationId}/uploads`, {
          method: "POST",
          body: JSON.stringify({
            name: file.name,
            size_bytes: file.size,
            content_type: file.type || "application/octet-stream",
            rename_on_conflict: true,
          }),
          timeoutMs: 15_000,
        })) as Response;
        if (!created.ok) throw new Error("Library could not accept this file.");
        let upload = (await created.json()) as {
          id: string;
          name?: string;
          chunk_size: number;
          total_chunks: number;
          received_chunks: number[];
          status: string;
          file_id?: string | null;
          extraction_status?: ComposerExtractionStatus | null;
          error?: string | null;
        };
        for (let index = 0; index < upload.total_chunks; index += 1) {
          if (upload.received_chunks.includes(index)) continue;
          const chunk = file.slice(
            index * upload.chunk_size,
            Math.min(file.size, (index + 1) * upload.chunk_size),
          );
          const response = (await fetchWithAuth(
            `/deepspace/library/${conversationId}/uploads/${upload.id}/chunks/${index}`,
            { method: "PUT", body: chunk, signal: controller.signal, timeoutMs: 120_000 },
          )) as Response;
          if (!response.ok) throw new Error("A secure upload chunk was rejected.");
          upload = await response.json();
          setAttachments((current) =>
            current.map((item) =>
              item.id === localId
                ? {
                    ...item,
                    uploadId: upload.id,
                    loaded: Math.min(file.size, (index + 1) * upload.chunk_size),
                  }
                : item,
            ),
          );
        }
        const complete = (await fetchWithAuth(
          `/deepspace/library/${conversationId}/uploads/${upload.id}/complete`,
          { method: "POST", timeoutMs: 15_000 },
        )) as Response;
        if (!complete.ok) throw new Error("Library could not process this file.");
        upload = await complete.json();
        setAttachments((current) =>
          current.map((item) => (item.id === localId ? { ...item, status: "processing" } : item)),
        );
        for (let attempt = 0; attempt < 180 && upload.status !== "completed"; attempt += 1) {
          if (upload.status === "failed" || upload.status === "cancelled")
            throw new Error(upload.error || "Library processing failed.");
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          const status = (await fetchWithAuth(
            `/deepspace/library/${conversationId}/uploads/${upload.id}`,
            { timeoutMs: 8_000 },
          )) as Response;
          if (!status.ok) throw new Error("Library upload status is unavailable.");
          upload = await status.json();
        }
        if (upload.status !== "completed" || !upload.file_id)
          throw new Error("The file is still processing. Please try again shortly.");
        setAttachments((current) =>
          current.map((item) =>
            item.id === localId
              ? {
                  ...item,
                  id: upload.file_id!,
                  name: upload.name || item.name,
                  status: "ready",
                  extractionStatus: upload.extraction_status ?? null,
                }
              : item,
          ),
        );
        if (upload.extraction_status?.state === "processing" && upload.file_id) {
          const uploadId = upload.id;
          const fileId = upload.file_id;
          // Keep the attachment sendable as soon as the private file exists.
          // Track optional OCR in the background so the composer never waits
          // for a parser to finish before allowing a vision/file request.
          void (async () => {
            for (let attempt = 0; attempt < 90; attempt += 1) {
              await new Promise((resolve) => window.setTimeout(resolve, 2_000));
              try {
                const response = (await fetchWithAuth(
                  `/deepspace/library/${conversationId}/uploads/${uploadId}`,
                  { timeoutMs: 8_000 },
                )) as Response;
                if (!response.ok) break;
                const latest = (await response.json()) as {
                  extraction_status?: ComposerExtractionStatus | null;
                };
                const extractionStatus = latest.extraction_status ?? null;
                setAttachments((current) =>
                  current.map((item) =>
                    item.id === fileId ? { ...item, extractionStatus } : item,
                  ),
                );
                if (extractionStatus?.state !== "processing") break;
              } catch {
                break;
              }
            }
          })();
        }
        window.dispatchEvent(
          new CustomEvent("deepspace-library-updated", { detail: { conversationId } }),
        );
      } catch (error) {
        const cancelled = controller.signal.aborted;
        setAttachments((current) =>
          current.map((item) =>
            item.id === localId
              ? {
                  ...item,
                  status: "error",
                  error: cancelled
                    ? "Upload cancelled."
                    : error instanceof Error
                      ? error.message
                      : "Upload failed.",
                }
              : item,
          ),
        );
      } finally {
        delete uploadControllersRef.current[localId];
      }
    }
  };
  const cancelAttachment = async (item: ComposerAttachment) => {
    uploadControllersRef.current[item.id]?.abort();
    if (item.uploadId && conversationId)
      await fetchWithAuth(`/deepspace/library/${conversationId}/uploads/${item.uploadId}/cancel`, {
        method: "POST",
        timeoutMs: 15_000,
      });
  };
  const retryAttachment = (item: ComposerAttachment) => {
    removeAttachment(item.id);
    if (item.file) void importAttachments([item.file]);
  };
  const openLibraryPicker = async () => {
    if (!conversationId || editingQueuedTurnId) return;
    const response = (await fetchWithAuth(`/deepspace/library/${conversationId}/entries`, {
      timeoutMs: 8_000,
    })) as Response;
    if (response.ok)
      setLibraryFiles(((await response.json()) as { files: typeof libraryFiles }).files ?? []);
    setLibraryPickerOpen(true);
  };
  const attachLibraryFile = (file: {
    id: string;
    name: string;
    content_type: string;
    size_bytes: number;
    extraction_status?: ComposerExtractionStatus | null;
  }) => {
    setAttachments((current) =>
      current.some((item) => item.id === file.id) || current.length >= 10
        ? current
        : [
            ...current,
            {
              ...file,
              type: file.content_type,
              size: file.size_bytes,
              status: "ready",
              extractionStatus: file.extraction_status ?? null,
            },
          ],
    );
    setLibraryPickerOpen(false);
  };
  const removeAttachment = (id: string) =>
    setAttachments((current) => {
      const removed = current.find((item) => item.id === id);
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return current.filter((item) => item.id !== id);
    });
  const submitWithAttachments = async () => {
    const ready = attachments.filter((item) => item.status === "ready");
    if (attachments.some((item) => item.status === "uploading" || item.status === "processing"))
      return;
    if (editingQueuedTurnId) {
      await onSaveQueueEdit?.(editingQueuedTurnId, query);
      return;
    }
    onSubmit(
      ready.map((item) => ({
        id: item.id,
        name: item.name,
        content_type: item.type || "application/octet-stream",
        size_bytes: item.size,
      })),
    );
    setAttachments([]);
  };
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
        setModelSearch("");
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const visualPhase: DeepSpaceRuntimePhase = hasRuntimeError
    ? "error"
    : runtimePhase === "idle" && query.trim()
      ? "typing"
      : runtimePhase;
  const toolKind = /search|web|searx|browse/i.test(activeToolName ?? "")
    ? "web"
    : /note[_-]?read|read|fetch|load|inspect/i.test(activeToolName ?? "")
      ? "read"
      : /note[_-]?write|write|insert|update|append/i.test(activeToolName ?? "")
        ? "write"
        : "default";
  const contextRatio =
    contextLimit && contextLimit > 0
      ? Math.min(1, Math.max(0, (contextUsedTokens ?? 0) / contextLimit))
      : 0;
  const hasContextLimit = Boolean(contextLimit && contextLimit > 0);
  const providerUsageAvailable = providerUsage?.usage_source === "provider";
  const providerTurnUsageAvailable = providerTurnUsage?.usage_source === "provider";
  const providerUsageScopeLabel =
    providerUsageScope === "latest_reported_round"
      ? "latest reported model round"
      : providerUsageScope === "turn_total"
        ? "whole turn"
        : "not reported";
  const tokenCategorySourceLabel =
    tokenCategorySource === "serialized_request_estimate"
      ? "local serialized estimate"
      : tokenCategorySource || "unavailable";
  const adaptiveBudgetLabel = (value: number | null | undefined) =>
    typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "not allocated";
  const runtimeStyle = {
    "--deepspace-context-ratio": contextRatio,
    "--deepspace-context-hue": Math.round(155 - contextRatio * 155),
    // Keep animation timing stable while tokens arrive. Changing duration on
    // every streamed token restarts the compositor timeline and appears as
    // border jitter/blinking on slower devices.
    "--deepspace-receive-duration": "1.2s",
  } as CSSProperties;

  const borderHighlight = "border-transparent shadow-[0_0_15px_rgba(16,185,129,0.18)]";

  const shellPadding = "p-2.5 sm:p-3";
  const composerShell = `bg-surface-1/35 backdrop-blur-md border transition-[box-shadow,background-color,border-color] duration-300 ${
    visualPhase === "idle" || visualPhase === "typing"
      ? borderHighlight
      : visualPhase === "error"
        ? "border-red-400/55 shadow-[0_0_24px_rgba(248,113,113,0.16)]"
        : "border-transparent shadow-[0_0_24px_rgba(34,211,238,0.12)]"
  }`;
  const textareaClass =
    "min-h-[52px] rounded-[1rem] bg-transparent px-3 py-2 text-[14px] leading-6";
  const pillClass =
    "theme-pill !rounded-[0.5rem] h-8 border-primary/15 bg-primary/5 px-2.5 text-[10px] font-semibold tracking-wide";
  const normalizedModelSearch = modelSearch.trim().toLocaleLowerCase();
  const selectedModelMetadata = selectedProviderId
    ? availableModels.find(
        (model) => model.modelName === modelName && model.providerId === selectedProviderId,
      )
    : availableModels.find((model) => model.modelName === modelName);
  const filteredModels = useMemo(
    () =>
      availableModels.filter((model) => {
        if (!normalizedModelSearch) return true;
        return [
          model.displayName,
          model.modelName,
          model.providerName,
          model.providerType,
          model.providerId,
          model.quantization,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase().includes(normalizedModelSearch));
      }),
    [availableModels, normalizedModelSearch],
  );
  const providerGroups = useMemo(() => {
    const groups = new Map<
      string,
      {
        providerId: string;
        providerName: string;
        providerType?: string;
        models: typeof filteredModels;
      }
    >();

    for (const model of filteredModels) {
      const group = groups.get(model.providerId);
      if (group) {
        group.models.push(model);
      } else {
        groups.set(model.providerId, {
          providerId: model.providerId,
          providerName:
            model.providerName?.trim() || model.providerType?.trim() || model.providerId,
          providerType: model.providerType,
          models: [model],
        });
      }
    }

    const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });
    return Array.from(groups.values())
      .map((group) => ({
        ...group,
        models: [...group.models].sort(
          (left, right) =>
            collator.compare(left.displayName, right.displayName) ||
            collator.compare(left.modelName, right.modelName),
        ),
      }))
      .sort(
        (left, right) =>
          collator.compare(left.providerName, right.providerName) ||
          collator.compare(left.providerId, right.providerId),
      );
  }, [filteredModels]);
  const defaultExpandedProviderId = providerGroups[0]?.providerId ?? null;
  const expandedProviderId =
    modelGroupExpansion?.search === normalizedModelSearch &&
    (modelGroupExpansion.providerId === null ||
      providerGroups.some((group) => group.providerId === modelGroupExpansion.providerId))
      ? modelGroupExpansion.providerId
      : defaultExpandedProviderId;
  const advertisedEfforts = (selectedModelMetadata?.supportedReasoningEfforts ?? []).filter(
    isValidReasoningEffort,
  );
  const reasoningOptions: Array<ReasoningEffort | null> = selectedModelMetadata?.reasoningToggleOnly
    ? [null, "medium"]
    : selectedModelMetadata?.reasoningCapabilitiesKnown
      ? [...(selectedModelMetadata.reasoningAlwaysOn ? [] : [null]), ...advertisedEfforts]
      : [null];
  if (reasoningOptions.length === 0) reasoningOptions.push(null);
  const formatReasoningEffort = (effort: ReasoningEffort) =>
    formatReasoningEffortLabel(effort, selectedModelMetadata?.reasoningEffortValues?.[effort]);
  const effortColor = (effort: ReasoningEffort | null) =>
    effort === "low"
      ? "bg-emerald-400"
      : effort === "medium"
        ? "bg-cyan-400"
        : effort === "high"
          ? "bg-fuchsia-400"
          : effort
            ? "bg-amber-400"
            : "bg-white/30";
  return (
    <div className="border-glass-border/60 sticky bottom-0 z-20 w-full border-t bg-transparent px-3 pt-3 pb-0 sm:px-5">
      <AnimatePresence initial={false}>
        {taskProgress?.tasks.length ? (
          <DeepSpaceTaskPlanDrawer
            key="conversation-task-plan"
            progress={taskProgress}
            isStreaming={isStreaming}
          />
        ) : null}
      </AnimatePresence>
      <div
        className={`deepspace-composer-runtime relative mx-auto w-full max-w-[min(100%,74rem)] overflow-visible ${runtimeLegendOpen ? "z-[100]" : "z-0"}`}
        data-runtime-phase={visualPhase}
        data-runtime-tool={toolKind}
        style={runtimeStyle}
      >
        <div
          aria-hidden="true"
          className="deepspace-composer-border-trace pointer-events-none absolute inset-0 z-20 overflow-hidden rounded-[1.2rem]"
          style={
            {
              padding: "1.5px",
              WebkitMask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
              WebkitMaskComposite: "xor",
              maskComposite: "exclude",
            } as CSSProperties
          }
        >
          <div
            aria-hidden="true"
            className="deepspace-composer-border-gradient absolute -inset-[200%]"
          />
          {visualPhase === "tool_calling" && (
            <div className="absolute inset-0" aria-hidden="true">
              {["#22d3ee", "#2dd4bf", "#34d399"].map((color, index) => (
                <span
                  key={color}
                  className="deepspace-composer-tool-trace absolute inset-0"
                  style={
                    {
                      "--deepspace-trace-color": color,
                      animationDelay: `${index * -0.42}s`,
                    } as CSSProperties
                  }
                />
              ))}
            </div>
          )}
          {visualPhase === "tool_calling" && toolKind === "web" && (
            <div className="deepspace-composer-search-particles" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          )}
        </div>

        <div
          className={`relative rounded-[1.2rem] shadow-xl ${
            runtimeLegendOpen
              ? "z-[110]"
              : modelDropdownOpen || contextDialogOpen || reasoningDropdownOpen
                ? "z-[80]"
                : "z-10"
          } ${composerShell} ${shellPadding}`}
        >
          {queuePaused || queuedTurns.length || changedFiles.length ? (
            <div className="mb-2 overflow-hidden rounded-t-xl border border-slate-300/80 bg-white/95 shadow-sm dark:border-cyan-300/20 dark:bg-cyan-950/40">
              {queuePaused || queuedTurns.length ? (
                <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2 text-[11px] dark:border-cyan-300/15">
                  <span
                    className={
                      queuePaused
                        ? "font-semibold text-amber-700 dark:text-amber-200"
                        : "font-semibold text-slate-700 dark:text-cyan-100/75"
                    }
                  >
                    {queuePaused ? "Queue paused" : "Queue active"}
                  </span>
                  {queuePaused && queuePauseReason ? (
                    <span
                      className="min-w-0 flex-1 truncate text-amber-800/80 dark:text-amber-100/60"
                      title={queuePauseReason}
                    >
                      {queuePauseReason}
                    </span>
                  ) : (
                    <span className="flex-1" />
                  )}
                  {queuePaused ? (
                    <button
                      type="button"
                      onClick={onResumeQueue}
                      disabled={queueAction !== null}
                      className="shrink-0 rounded-md border border-emerald-600/40 bg-emerald-50 px-2 py-1 text-emerald-800 transition hover:bg-emerald-100 disabled:cursor-wait disabled:opacity-60 dark:border-emerald-300/25 dark:bg-transparent dark:text-emerald-200/85 dark:hover:bg-emerald-300/10"
                    >
                      {queueAction === "resume"
                        ? "Resuming…"
                        : queueFailedRequestId
                          ? "Continue queued prompts"
                          : "Resume queue"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={onPauseQueue}
                      disabled={queueAction !== null}
                      className="shrink-0 rounded-md border border-slate-300 bg-slate-50 px-2 py-1 text-slate-700 hover:bg-slate-100 dark:border-cyan-300/20 dark:bg-transparent dark:text-cyan-100/70 dark:hover:bg-cyan-300/10"
                    >
                      Pause queue
                    </button>
                  )}
                  {queuedTurns.length || queuePaused ? (
                    <button
                      type="button"
                      onClick={onClearQueue}
                      disabled={queueAction !== null}
                      aria-label="Clear pending queue"
                      title="Clear pending queue (chat history is kept)"
                      className="shrink-0 rounded-md border border-red-300/70 bg-red-50 px-2 py-1 text-red-700 hover:bg-red-100 dark:border-red-300/20 dark:bg-transparent dark:text-red-200/85 dark:hover:bg-red-300/10"
                    >
                      <Trash2 size={13} aria-hidden="true" />
                      <span className="sr-only">Clear queue</span>
                    </button>
                  ) : null}
                </div>
              ) : null}
              {changedFiles.length ? (
                <button
                  type="button"
                  onClick={() => setReviewOpen((open) => !open)}
                  className="flex w-full items-center justify-between px-3 py-2 text-xs text-cyan-100/80 hover:bg-cyan-300/[0.06]"
                >
                  <span>
                    <strong>
                      {changedFiles.length} file{changedFiles.length === 1 ? "" : "s"} changed
                    </strong>
                    <span className="ml-2 text-emerald-300">
                      +{changedFiles.reduce((total, file) => total + file.additions, 0)}
                    </span>
                    <span className="ml-1 text-red-300">
                      -{changedFiles.reduce((total, file) => total + file.deletions, 0)}
                    </span>
                  </span>
                  <span>{reviewOpen ? "Hide review" : "Review"}</span>
                </button>
              ) : null}
              {reviewOpen ? (
                <div className="border-t border-cyan-300/15 px-3 py-2 text-[11px] text-cyan-100/70">
                  {changedFiles.map((file) => (
                    <div key={file.path} className="flex justify-between gap-3">
                      <span className="truncate">{file.path}</span>
                      <span className="shrink-0 text-emerald-300">+{file.additions}</span>
                      <span className="shrink-0 text-red-300">-{file.deletions}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {queuedTurns.length ? (
                <div
                  className="border-t border-slate-200 px-2 py-1.5 dark:border-cyan-300/15"
                  aria-label="Queued messages"
                  aria-live="polite"
                >
                  {editingQueuedTurnId ? (
                    <div className="flex items-center gap-2 rounded-md border border-cyan-300/20 bg-cyan-300/[0.06] px-2 py-2 text-[11px] text-cyan-100/80">
                      <span className="min-w-0 flex-1">
                        Editing a queued prompt. Saving keeps its current place in line; its
                        existing attachments stay attached.
                      </span>
                      <button
                        type="button"
                        onClick={onCancelQueueEdit}
                        disabled={queueAction !== null}
                        className="shrink-0 rounded-md px-2 py-1 font-medium text-cyan-100 transition hover:bg-cyan-200/10 disabled:opacity-50"
                      >
                        Cancel edit
                      </button>
                    </div>
                  ) : null}
                  <AnimatePresence initial={false}>
                    {queuedTurns.map((turn, index) => (
                      <motion.div
                        key={turn.clientRequestId}
                        data-queue-turn-id={turn.clientRequestId}
                        layout
                        initial={reduceMotion ? false : { opacity: 0, y: 7, scale: 0.985 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={
                          reduceMotion
                            ? { opacity: 0 }
                            : { opacity: 0, x: -12, height: 0, marginTop: 0, marginBottom: 0 }
                        }
                        transition={
                          reduceMotion
                            ? { duration: 0.01 }
                            : {
                                layout: { type: "spring", stiffness: 480, damping: 38 },
                                default: { duration: 0.18, ease: "easeOut" },
                              }
                        }
                        className="flex max-w-full items-center gap-2 rounded-md px-2 py-1.5 text-[11px] text-slate-700 hover:bg-slate-50 dark:text-cyan-100/80 dark:hover:bg-cyan-300/[0.06]"
                      >
                        <span className="text-slate-400 dark:text-cyan-200/60">↳</span>
                        <span className="min-w-0 flex-1 truncate">
                          {turn.regenerateMessageId ? "Regenerate reply: " : ""}
                          {turn.prompt}
                        </span>
                        <span className="shrink-0 text-[9px] font-semibold tracking-wide text-slate-500 uppercase dark:text-cyan-200/55">
                          {turn.status === "queued"
                            ? "Queued"
                            : turn.status === "running"
                              ? "Running"
                              : turn.status === "awaiting_user"
                                ? "Waiting for answer"
                                : turn.status === "awaiting_approval"
                                  ? "Waiting for approval"
                                  : turn.status === "failed"
                                    ? "Failed"
                                    : "Stopping"}
                        </span>
                        {turn.status === "queued" &&
                        !editingQueuedTurnId &&
                        !turn.regenerateMessageId ? (
                          <button
                            type="button"
                            onClick={() => onEditQueuedTurn?.(turn.clientRequestId)}
                            disabled={
                              queueAction !== null ||
                              attachments.some(
                                (item) =>
                                  item.status === "uploading" || item.status === "processing",
                              )
                            }
                            aria-label={`Edit queued message ${index + 1}`}
                            title="Edit this pending prompt without changing its queue position"
                            className="flex shrink-0 items-center gap-1 text-cyan-700 transition hover:text-cyan-900 disabled:cursor-wait disabled:opacity-50 dark:text-cyan-100/75 dark:hover:text-white"
                          >
                            <Pencil size={11} aria-hidden="true" /> Edit
                          </button>
                        ) : null}
                        {turn.status === "queued" && !editingQueuedTurnId ? (
                          <button
                            type="button"
                            onClick={() => onSteerQueuedTurn?.(turn.clientRequestId)}
                            disabled={queueAction !== null}
                            title="Move this prompt ahead of ordinary FIFO items"
                            className="text-slate-600 transition hover:text-slate-900 disabled:opacity-50 dark:text-cyan-100/65 dark:hover:text-cyan-100"
                          >
                            ↳ Steer
                          </button>
                        ) : null}
                        {turn.status !== "failed" ? (
                          <button
                            type="button"
                            onClick={() => onCancelQueuedTurn?.(turn.clientRequestId)}
                            className="text-slate-400 hover:text-red-600 dark:text-cyan-100/45 dark:hover:text-red-200"
                            aria-label={`Remove queued message ${index + 1}`}
                            title="Remove from queue"
                          >
                            <Trash2 size={12} />
                          </button>
                        ) : null}
                        {turn.status === "failed" && turn.error ? (
                          <span
                            className="max-w-[42%] truncate text-red-700/80 dark:text-red-200/70"
                            title={turn.error}
                          >
                            {turn.error}
                          </span>
                        ) : null}
                        {turn.status === "failed" ? (
                          <button
                            type="button"
                            onClick={() => onRetryFailedTurn?.(turn.clientRequestId)}
                            disabled={queueAction !== null}
                            title="Retry from the saved checkpoint when available. If it expired, restart this prompt from the beginning; completed actions may repeat."
                            className="shrink-0 text-cyan-800 transition hover:text-cyan-950 disabled:cursor-wait disabled:opacity-50 dark:text-cyan-200 dark:hover:text-cyan-100"
                          >
                            {queueAction === turn.clientRequestId ? "Retrying…" : "Retry prompt"}
                          </button>
                        ) : null}
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              ) : null}
            </div>
          ) : null}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="sr-only"
            disabled={editingQueuedTurnId !== null}
            onChange={(event) => {
              if (event.target.files) void importAttachments(event.target.files);
              event.target.value = "";
            }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            disabled={editingQueuedTurnId !== null}
            onChange={(event) => {
              if (event.target.files) void importAttachments(event.target.files);
              event.target.value = "";
            }}
          />
          {attachmentError ? (
            <p className="mb-2 rounded-lg border border-amber-400/40 bg-amber-50 px-2 py-1 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
              {attachmentError}
              <button
                type="button"
                className="ml-2 underline"
                onClick={() => setAttachmentError(null)}
              >
                Dismiss
              </button>
            </p>
          ) : null}
          {attachments.length ? (
            <div
              className="mb-2 flex max-h-28 flex-wrap gap-2 overflow-y-auto px-1"
              aria-label="Files shared with this message"
            >
              {attachments.map((item) => (
                <div
                  key={item.id}
                  className="group flex w-36 items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-50/80 p-2 text-left text-[10px] text-emerald-950 shadow-sm dark:bg-emerald-950/30 dark:text-emerald-100"
                >
                  <button
                    type="button"
                    onClick={() => setAttachmentPreview(item)}
                    className="flex min-w-0 flex-1 items-center gap-2"
                    title={`Preview ${item.name}`}
                  >
                    {item.previewUrl ? (
                      <img src={item.previewUrl} alt="" className="h-9 w-9 rounded object-cover" />
                    ) : (
                      <FileText className="h-5 w-5 shrink-0 text-emerald-600" />
                    )}
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{item.name}</span>
                      <span className="block text-emerald-700/70">
                        {item.status === "ready"
                          ? (attachmentExtractionLabel(item.extractionStatus) ?? "Saved to Library")
                          : item.status === "error"
                            ? item.error
                            : item.status === "processing"
                              ? "Scanning…"
                              : `Uploading ${Math.round(((item.loaded ?? 0) / Math.max(1, item.size)) * 100)}%`}
                      </span>
                    </span>
                  </button>
                  {item.status === "error" && item.file ? (
                    <button
                      type="button"
                      onClick={() => retryAttachment(item)}
                      className="shrink-0 text-emerald-700 hover:text-emerald-900"
                      aria-label={`Retry ${item.name}`}
                    >
                      <RotateCw size={13} />
                    </button>
                  ) : null}
                  {item.status === "uploading" || item.status === "processing" ? (
                    <button
                      type="button"
                      onClick={() => void cancelAttachment(item)}
                      className="shrink-0 text-amber-700 hover:text-rose-600"
                      aria-label={`Cancel ${item.name}`}
                    >
                      <X size={13} />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => removeAttachment(item.id)}
                      className="shrink-0 text-emerald-700 hover:text-rose-600"
                      aria-label={`Remove ${item.name}`}
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : null}
          <div className="flex items-start gap-2">
            <div className="deepspace-attachment-actions flex shrink-0 gap-1.5">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                onMouseEnter={(event) =>
                  showAttachmentTooltip(
                    "files",
                    "deepspace-attach-files-tooltip",
                    "Attach files or paste a screenshot",
                    event.currentTarget,
                  )
                }
                onMouseLeave={() => setActiveAttachmentTooltip(null)}
                onFocus={(event) =>
                  showAttachmentTooltip(
                    "files",
                    "deepspace-attach-files-tooltip",
                    "Attach files or paste a screenshot",
                    event.currentTarget,
                  )
                }
                onBlur={() => setActiveAttachmentTooltip(null)}
                disabled={!conversationId || editingQueuedTurnId !== null}
                className="deepspace-attachment-action"
                aria-label="Attach files from your device"
                aria-describedby={
                  activeAttachmentTooltip?.kind === "files"
                    ? "deepspace-attach-files-tooltip"
                    : undefined
                }
              >
                <Paperclip size={16} />
              </button>
              <button
                type="button"
                onClick={() => cameraInputRef.current?.click()}
                onMouseEnter={(event) =>
                  showAttachmentTooltip(
                    "camera",
                    "deepspace-take-photo-tooltip",
                    "Take a photo",
                    event.currentTarget,
                  )
                }
                onMouseLeave={() => setActiveAttachmentTooltip(null)}
                onFocus={(event) =>
                  showAttachmentTooltip(
                    "camera",
                    "deepspace-take-photo-tooltip",
                    "Take a photo",
                    event.currentTarget,
                  )
                }
                onBlur={() => setActiveAttachmentTooltip(null)}
                disabled={!conversationId || editingQueuedTurnId !== null}
                className="deepspace-attachment-action"
                aria-label="Take a photo"
                aria-describedby={
                  activeAttachmentTooltip?.kind === "camera"
                    ? "deepspace-take-photo-tooltip"
                    : undefined
                }
              >
                <Camera size={16} />
              </button>
              <button
                type="button"
                onClick={() => void openLibraryPicker()}
                onMouseEnter={(event) =>
                  showAttachmentTooltip(
                    "library",
                    "deepspace-attach-library-tooltip",
                    "Attach from Library",
                    event.currentTarget,
                  )
                }
                onMouseLeave={() => setActiveAttachmentTooltip(null)}
                onFocus={(event) =>
                  showAttachmentTooltip(
                    "library",
                    "deepspace-attach-library-tooltip",
                    "Attach from Library",
                    event.currentTarget,
                  )
                }
                onBlur={() => setActiveAttachmentTooltip(null)}
                disabled={!conversationId || editingQueuedTurnId !== null}
                className="deepspace-attachment-action"
                aria-label="Attach an existing Library file"
                aria-describedby={
                  activeAttachmentTooltip?.kind === "library"
                    ? "deepspace-attach-library-tooltip"
                    : undefined
                }
              >
                <FolderOpen size={16} />
              </button>
            </div>
            <textarea
              ref={textareaRef}
              rows={2}
              value={query}
              onChange={(event) => onQueryChange(event.target.value.slice(0, 4000))}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submitWithAttachments();
                }
              }}
              placeholder={editingQueuedTurnId ? "Edit queued prompt…" : "Message DeepSpace..."}
              onPaste={(event) => {
                const files = Array.from(event.clipboardData.files);
                if (files.length) {
                  event.preventDefault();
                  if (!editingQueuedTurnId) void importAttachments(files);
                }
              }}
              onDrop={(event) => {
                const files = Array.from(event.dataTransfer.files);
                if (files.length) {
                  event.preventDefault();
                  if (!editingQueuedTurnId) void importAttachments(files);
                }
              }}
              onDragOver={(event) => event.preventDefault()}
              className={`text-foreground placeholder:text-foreground/30 max-h-[8.5rem] w-full resize-none overflow-y-hidden border-none bg-transparent outline-none ${textareaClass}`}
            />
          </div>

          <div className="text-muted-foreground relative mt-1 px-2 text-[9px] dark:text-white/40">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setContextDialogOpen((open) => !open)}
                className="deepspace-context-label flex shrink-0 items-center gap-1 tracking-[0.14em] uppercase transition-colors hover:text-cyan-200"
                aria-expanded={contextDialogOpen}
                aria-label="Show context usage details"
              >
                <Gauge size={11} />
                Request context (est.)
              </button>
              <span className="deepspace-context-values min-w-0 overflow-x-auto whitespace-nowrap tabular-nums">
                {(contextUsedTokens ?? 0).toLocaleString()} /{" "}
                {hasContextLimit ? contextLimit?.toLocaleString() : "—"} ·{" "}
                {(requestInputTokens ?? 0).toLocaleString()} model in ·{" "}
                {(requestOutputTokens ?? 0).toLocaleString()} model out ·{" "}
                {hasContextLimit ? `${Math.round(contextRatio * 100)}%` : "—"}
                {isStreaming ? (
                  <DeepSpaceLiveOutputRate
                    outputTokens={liveOutputTokens}
                    startedAtMs={liveOutputStartedAtMs}
                  />
                ) : null}
              </span>
            </div>
            <div
              className="deepspace-context-progress mt-1 h-1 w-full overflow-hidden rounded-full bg-cyan-950/15 ring-1 ring-cyan-900/15 dark:bg-cyan-950/15"
              role="progressbar"
              aria-label="Estimated provider context usage"
              aria-valuemin={0}
              aria-valuemax={contextLimit ?? undefined}
              aria-valuenow={contextUsedTokens ?? 0}
              aria-valuetext={
                hasContextLimit
                  ? `${(contextUsedTokens ?? 0).toLocaleString()} of ${contextLimit?.toLocaleString()} estimated provider context tokens`
                  : "Estimated provider context limit unavailable"
              }
            >
              <div
                className="deepspace-context-progress-fill h-full rounded-full bg-linear-to-r from-cyan-400 via-teal-400 to-emerald-400 transition-[width] duration-300 ease-out"
                style={{ width: `${contextRatio * 100}%` }}
              />
            </div>
            <AnimatePresence>
              {contextDialogOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 5, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 3, scale: 0.98 }}
                  role="dialog"
                  aria-label="Context usage details"
                  className="deepspace-diagnostics-card border-glass-border bg-surface-1 text-muted-foreground absolute right-0 bottom-full z-[75] mb-2 w-[min(28rem,calc(100vw-2rem))] rounded-2xl border p-4 text-[10px] leading-4 shadow-2xl"
                >
                  <div className="deepspace-diagnostics-header text-foreground mb-3 flex items-center justify-between gap-3 pb-3 text-[11px] font-semibold">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="deepspace-diagnostics-icon flex h-7 w-7 shrink-0 items-center justify-center rounded-lg">
                        <Gauge size={14} />
                      </span>
                      <span>Request diagnostics</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setContextDialogOpen(false)}
                      className="deepspace-diagnostics-close text-muted-foreground hover:text-foreground flex h-6 w-6 shrink-0 items-center justify-center rounded-full transition-colors"
                      aria-label="Close context details"
                    >
                      ×
                    </button>
                  </div>
                  <div className="deepspace-diagnostics-metrics grid grid-cols-2 gap-2">
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--context rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Latest round context estimate
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(contextUsedTokens ?? 0).toLocaleString()} /{" "}
                        {hasContextLimit ? contextLimit?.toLocaleString() : "Unavailable"}
                      </strong>
                      <span className="deepspace-diagnostics-metric-percent ml-1">
                        ({Math.round(contextRatio * 100)}%)
                      </span>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--input rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Turn input estimate (all rounds)
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(requestInputTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--output rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Turn output estimate
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(requestOutputTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--remaining rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Safe remaining
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {hasContextLimit
                          ? (safeRemainingTokens ?? contextRemainingTokens ?? 0).toLocaleString()
                          : "Unavailable"}
                      </strong>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--session rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Session total (estimated)
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(sessionTotalTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--reserve rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Reserved output budget
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(reservedOutputTokens ?? maxOutputTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                  </div>
                  <p className="deepspace-diagnostics-description border-border text-muted-foreground mt-3 border-t pt-3">
                    DeepSpace keeps provider-neutral serialized estimates for every model round. The
                    latest round context is the current request sent to the provider; turn input and
                    output include earlier tool and recovery rounds. Provider tokenizers can differ,
                    so an exact count is shown only when the adapter reports it.
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Conversation: {(conversationVisibleTokens ?? 0).toLocaleString()} tokens ·{" "}
                    {(userVisibleInputTokens ?? 0).toLocaleString()} in ·{" "}
                    {(userVisibleOutputTokens ?? 0).toLocaleString()} out
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Local token estimate: system {systemContextTokens?.toLocaleString() ?? "—"} ·
                    schemas {toolSchemaTokens?.toLocaleString() ?? "—"} · results{" "}
                    {toolResultTokens?.toLocaleString() ?? "—"} · context{" "}
                    {uncachedInputTokens?.toLocaleString() ?? "—"}
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Provider usage ({providerUsageScopeLabel})
                    {providerUsageAvailable
                      ? `: input ${providerUsage?.input_tokens?.toLocaleString() ?? "—"} · output ${providerUsage?.output_tokens?.toLocaleString() ?? "—"} · cache read ${providerUsage?.cached_input_tokens?.toLocaleString() ?? "not reported"} · cache write ${providerUsage?.cache_write_input_tokens?.toLocaleString() ?? "not reported"}`
                      : ": not reported by this adapter"}
                    {providerUsageRoundCount && providerUsageRoundCount > 1
                      ? ` · ${providerUsageRoundCount} rounds reported`
                      : ""}
                  </p>
                  {providerTurnUsageAvailable ? (
                    <p className="text-muted-foreground mt-1">
                      Provider turn total ({providerUsageRoundCount ?? 0} reported rounds): input{" "}
                      {providerTurnUsage?.input_tokens?.toLocaleString() ?? "not complete"} · output{" "}
                      {providerTurnUsage?.output_tokens?.toLocaleString() ?? "not complete"} · cache
                      read{" "}
                      {providerTurnUsage?.cached_input_tokens?.toLocaleString() ?? "not complete"} ·
                      cache write{" "}
                      {providerTurnUsage?.cache_write_input_tokens?.toLocaleString() ??
                        "not complete"}
                    </p>
                  ) : null}
                  <p className="text-muted-foreground mt-1">
                    Adaptive budgets (latest round): history{" "}
                    {adaptiveBudgetLabel(adaptiveHistoryBudgetTokens)} · tool results{" "}
                    {adaptiveBudgetLabel(adaptiveToolResultBudgetTokens)}
                  </p>
                  <p className="text-muted-foreground mt-1 text-[9px]">
                    Estimate source: {tokenCategorySourceLabel}; turn input{" "}
                    {requestInputTokensSource === "serialized_request_estimate"
                      ? "serialized"
                      : requestInputTokensSource || "unavailable"}
                    ; turn output{" "}
                    {requestOutputTokensSource === "serialized_response_estimate"
                      ? "serialized"
                      : requestOutputTokensSource || "unavailable"}
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Prompt cache:{" "}
                    {providerUsageAvailable &&
                    (providerUsage?.cached_input_tokens != null ||
                      providerUsage?.cache_write_input_tokens != null)
                      ? `${promptCacheMode || "provider cache"} reported by provider`
                      : promptCacheStatus === "native_requested"
                        ? `${promptCacheMode} requested; provider did not report cache usage`
                        : promptCacheStatus === "unsupported"
                          ? "not supported by this adapter"
                          : promptCacheStatus === "disabled"
                            ? "disabled"
                            : promptCacheEligible
                              ? `${promptCacheMode} eligible; usage not reported yet`
                              : "not reported"}
                  </p>
                  <div className="deepspace-diagnostics-footer border-border mt-3 border-t pt-2.5">
                    <div className="text-muted-foreground flex items-center justify-between">
                      <span>
                        Status:{" "}
                        <span className="text-foreground">
                          {contextStatus ?? (hasContextLimit ? "normal" : "unavailable")}
                        </span>
                      </span>
                      {contextCompacted ? (
                        <span className="text-emerald-300">Compacted</span>
                      ) : null}
                    </div>
                    {contextEpoch ? (
                      <div className="text-muted-foreground mt-1 flex items-center justify-between">
                        <span>Context epoch {contextEpoch}</span>
                        <span className="text-cyan-700 dark:text-cyan-200">
                          {contextEpochReason === "compaction" || contextCompacted
                            ? "Rebalanced"
                            : contextSourceUpdates.length
                              ? "Updated"
                              : "Stable"}
                        </span>
                      </div>
                    ) : null}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <div className="border-glass-border/70 mt-2.5 flex items-center justify-between gap-3 border-t pt-2.5">
            <div className="flex min-w-0 flex-grow flex-wrap items-center gap-1.5 sm:gap-2">
              {/* Functional Model Dropdown */}
              <div ref={dropdownRef} className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setModelDropdownOpen((open) => {
                      if (open) setModelSearch("");
                      return !open;
                    });
                  }}
                  disabled={isStreaming}
                  className={`${pillClass} border-glass-border bg-surface-2 text-foreground/60 hover:text-foreground flex items-center gap-1.5 transition-all hover:bg-white/5 active:scale-95`}
                >
                  {isStreaming ? (
                    <motion.span
                      aria-hidden="true"
                      className="inline-flex text-cyan-300"
                      animate={{
                        rotate: [0, -8, 8, -4, 0],
                        scale: [1, 1.12, 1],
                        filter: [
                          "drop-shadow(0 0 0 rgba(103,232,249,0))",
                          "drop-shadow(0 0 5px rgba(103,232,249,.9))",
                          "drop-shadow(0 0 0 rgba(103,232,249,0))",
                        ],
                      }}
                      transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                    >
                      <Bot size={11} />
                    </motion.span>
                  ) : (
                    <Bot size={11} />
                  )}
                  <span className="max-w-[11rem] truncate">{modelName || "Select Model"}</span>
                  <ChevronDown
                    size={11}
                    className={`transition-transform duration-200 ${modelDropdownOpen ? "rotate-180" : ""}`}
                  />
                </button>

                <AnimatePresence>
                  {modelDropdownOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 6, scale: 0.98 }}
                      transition={{ duration: 0.16, ease: "easeOut" }}
                      className="deepspace-model-menu absolute bottom-full left-0 z-[100] mb-2 flex h-[min(22rem,calc(100dvh-2rem))] w-[min(31rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border p-1"
                    >
                      <div className="deepspace-model-menu-search-shell sticky top-0 z-10 p-1">
                        <input
                          type="search"
                          value={modelSearch}
                          onChange={(event) => setModelSearch(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Escape") {
                              setModelSearch("");
                              setModelDropdownOpen(false);
                            }
                          }}
                          autoFocus
                          placeholder="Search models..."
                          aria-label="Search models"
                          className="deepspace-model-menu-search h-8 w-full rounded-md border px-2.5 text-xs outline-none"
                        />
                      </div>
                      {providerGroups.length > 0 ? (
                        <div className="deepspace-model-menu-list min-h-0 flex-1 overflow-y-auto p-1">
                          {providerGroups.map((group) => {
                            const expanded = expandedProviderId === group.providerId;
                            const groupId = `deepspace-model-group-${group.providerId}`;
                            return (
                              <section
                                key={group.providerId}
                                className="deepspace-model-provider-group"
                              >
                                <button
                                  type="button"
                                  aria-expanded={expanded}
                                  aria-controls={groupId}
                                  onClick={() =>
                                    setModelGroupExpansion({
                                      search: normalizedModelSearch,
                                      providerId: expanded ? null : group.providerId,
                                    })
                                  }
                                  className="deepspace-model-provider-heading flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors"
                                >
                                  <span
                                    aria-hidden="true"
                                    className="deepspace-model-provider-mark flex h-7 w-7 shrink-0 items-center justify-center"
                                  >
                                    <ProviderLogo providerType={group.providerType} size={22} />
                                  </span>
                                  <span className="flex min-w-0 flex-1 flex-col">
                                    <span
                                      role="heading"
                                      aria-level={3}
                                      className="deepspace-model-provider-name truncate text-xs font-semibold"
                                    >
                                      {group.providerName}
                                    </span>
                                    {group.providerType && (
                                      <span className="deepspace-model-provider-type truncate text-[9px] tracking-wide uppercase">
                                        {group.providerType.replaceAll("_", " ")}
                                      </span>
                                    )}
                                  </span>
                                  <span className="deepspace-model-provider-count shrink-0 text-[10px] tabular-nums">
                                    {group.models.length}
                                  </span>
                                  <ChevronDown
                                    size={12}
                                    aria-hidden="true"
                                    className={`deepspace-model-provider-chevron shrink-0 transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
                                  />
                                </button>
                                {expanded && (
                                  <div
                                    id={groupId}
                                    role="group"
                                    aria-label={`${group.providerName} models`}
                                    className="deepspace-model-provider-models space-y-0.5 pb-1 pl-2"
                                  >
                                    {group.models.map((m) => {
                                      const selected =
                                        m.modelName === modelName &&
                                        (!selectedProviderId ||
                                          m.providerId === selectedProviderId);
                                      return (
                                        <button
                                          key={`${m.providerId}-${m.modelName}`}
                                          type="button"
                                          onClick={() => {
                                            onModelSelect?.(m.providerId, m.modelName);
                                            setModelDropdownOpen(false);
                                            setModelSearch("");
                                          }}
                                          className={`deepspace-model-menu-option flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-all ${
                                            selected
                                              ? "deepspace-model-menu-option--selected font-medium"
                                              : ""
                                          }`}
                                        >
                                          <span className="flex min-w-0 items-center gap-1.5 truncate">
                                            <span className="deepspace-model-menu-name truncate">
                                              {m.displayName}
                                            </span>
                                            {m.quantization && (
                                              <span className="deepspace-model-menu-quantization shrink-0 text-[9px] font-semibold tracking-wide uppercase">
                                                {m.quantization}
                                              </span>
                                            )}
                                          </span>
                                          {selected && (
                                            <Check
                                              size={11}
                                              className="deepspace-model-menu-check ml-2 flex-shrink-0"
                                            />
                                          )}
                                        </button>
                                      );
                                    })}
                                  </div>
                                )}
                              </section>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="deepspace-model-menu-empty px-2.5 py-3 text-xs italic">
                          {availableModels.length ? "No matching models" : "No models found"}
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <div className="relative flex-shrink-0">
                <button
                  type="button"
                  disabled={isStreaming}
                  onClick={() => setReasoningDropdownOpen((open) => !open)}
                  aria-label="Choose reasoning effort"
                  aria-expanded={reasoningDropdownOpen}
                  className={`${pillClass} bg-surface-2 text-foreground/70 hover:text-foreground flex items-center gap-1.5 border-white/10 transition-all hover:border-cyan-300/40`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${effortColor(reasoningEffort ?? null)}`}
                  />
                  Think{" "}
                  {!selectedModelMetadata?.reasoningCapabilitiesKnown
                    ? "Auto"
                    : selectedModelMetadata.reasoningAlwaysOn && advertisedEfforts.length === 0
                      ? "On"
                      : reasoningEffort
                        ? selectedModelMetadata.reasoningToggleOnly
                          ? "On"
                          : formatReasoningEffort(reasoningEffort)
                        : "Off"}
                  <ChevronDown size={11} className={reasoningDropdownOpen ? "rotate-180" : ""} />
                </button>
                <AnimatePresence>
                  {reasoningDropdownOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      className="deepspace-reasoning-menu border-glass-border text-foreground absolute bottom-full left-0 isolate z-[70] mb-2 min-w-[150px] rounded-xl border bg-[#f4fbf7] p-1 shadow-[0_16px_40px_rgba(0,0,0,0.45)] dark:bg-[#101612]"
                    >
                      {reasoningOptions.map((effort) => (
                        <button
                          key={effort ?? "off"}
                          type="button"
                          onClick={() => {
                            onReasoningEffortChange?.(effort);
                            setReasoningDropdownOpen(false);
                          }}
                          className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs ${reasoningEffort === effort ? "bg-cyan-400/15 text-cyan-200" : "text-foreground/75 hover:bg-foreground/[0.05]"}`}
                        >
                          <span className={`h-2 w-2 rounded-full ${effortColor(effort)}`} />
                          {!selectedModelMetadata?.reasoningCapabilitiesKnown
                            ? "Provider default"
                            : selectedModelMetadata.reasoningAlwaysOn &&
                                advertisedEfforts.length === 0
                              ? "On"
                              : effort
                                ? selectedModelMetadata.reasoningToggleOnly
                                  ? "On"
                                  : formatReasoningEffort(effort)
                                : "Off"}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Direct Voice Integration Controls */}
              <div
                className="relative flex h-8 items-center rounded-lg border border-white/10 bg-black/40 p-0.5 backdrop-blur-md"
                data-testid="deepspace-voice-controls"
              >
                {/* Dictation stays in the composer for review before sending. */}
                <div className="group relative">
                  <button
                    type="button"
                    onClick={dictationSessionOpen && sttActive ? onDictationPause : onSttToggle}
                    disabled={dictationControlPending}
                    className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                      sttActive
                        ? "border border-emerald-500/35 bg-emerald-500/25 text-emerald-400 shadow-[0_2px_8px_rgba(16,185,129,0.3)]"
                        : "border border-transparent text-white/40 hover:text-white/80"
                    }`}
                    aria-label={
                      dictationSessionOpen
                        ? sttActive
                          ? "Pause dictation"
                          : "Resume dictation"
                        : "Dictate to composer"
                    }
                    aria-pressed={sttActive}
                  >
                    {sttActive ? (
                      <Mic
                        size={13}
                        className={voiceState === "listening" ? "animate-pulse" : ""}
                      />
                    ) : (
                      <MicOff size={13} />
                    )}
                  </button>
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-[60] mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                    <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                      {dictationSessionOpen
                        ? sttActive
                          ? "Pause dictation"
                          : "Resume dictation"
                        : "Dictate to composer"}
                    </div>
                  </div>
                </div>

                {/* Voice conversation uses the active DeepSpace chat for both directions. */}
                <div className="group relative">
                  <button
                    type="button"
                    onClick={onTtsToggle}
                    className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                      ttsActive
                        ? "bg-primary/20 text-primary border-primary/35 border shadow-[0_2px_8px_rgba(var(--primary),0.3)]"
                        : "border border-transparent text-white/40 hover:text-white/80"
                    }`}
                    aria-label="Voice conversation"
                    aria-pressed={ttsActive}
                  >
                    {ttsActive ? (
                      <Volume2
                        size={13}
                        className={voiceState === "speaking" ? "animate-bounce" : ""}
                      />
                    ) : (
                      <VolumeX size={13} />
                    )}
                  </button>
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-[60] mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                    <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                      Voice conversation
                    </div>
                  </div>
                </div>

                {dictationSessionOpen && (
                  <>
                    <button
                      type="button"
                      onClick={onDictationFinish}
                      disabled={dictationControlPending}
                      className="flex h-7 w-7 items-center justify-center rounded-[0.35rem] text-emerald-300 transition-colors hover:bg-emerald-400/10 hover:text-emerald-200"
                      aria-label="Finish dictation"
                      title="Finish dictation"
                    >
                      <Check size={13} />
                    </button>
                  </>
                )}

                <DeepSpaceVoicePresence state={voiceState} activityLevel={voiceActivityLevel} />
              </div>

              {voiceLabel && (
                <span className="ml-0.5 max-w-[120px] truncate text-[10px] font-semibold tracking-wide text-white/45">
                  {voiceLabel}
                </span>
              )}
              {dictationSessionOpen && (
                <span
                  className="shrink-0 text-[9px] text-white/40 tabular-nums"
                  aria-label={`Dictation time ${formatDictationElapsed(dictationElapsedSeconds)} of 10:00`}
                  data-testid="dictation-elapsed"
                >
                  {formatDictationElapsed(dictationElapsedSeconds)} / 10:00
                </span>
              )}
            </div>

            <div className="relative flex-shrink-0">
              <button
                type="button"
                onClick={() => setRuntimeLegendOpen((open) => !open)}
                aria-label="Show DeepSpace status legend"
                aria-expanded={runtimeLegendOpen}
                title="DeepSpace status legend"
                className={`deepspace-composer-control flex h-8 w-8 items-center justify-center rounded-lg border transition-all duration-200 ${
                  runtimeLegendOpen
                    ? "border-cyan-600/40 bg-cyan-100 text-cyan-800 dark:border-cyan-400/45 dark:bg-cyan-400/15 dark:text-cyan-200"
                    : "border-slate-300 bg-white/80 text-slate-500 hover:border-cyan-500/40 hover:text-cyan-700 dark:border-white/10 dark:bg-black/30 dark:text-white/45 dark:hover:border-cyan-400/30 dark:hover:text-cyan-200"
                }`}
              >
                <CircleHelp size={14} />
              </button>
              <AnimatePresence>
                {runtimeLegendOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 6, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.98 }}
                    transition={{ duration: 0.14, ease: "easeOut" }}
                    role="dialog"
                    aria-label="DeepSpace status legend"
                    className="absolute right-0 bottom-full isolate z-[70] mb-2 w-[min(19rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white/95 p-3 text-[10px] leading-4 text-slate-600 shadow-2xl ring-1 ring-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-[#0b1411]/95 dark:text-white/65 dark:ring-black/50"
                  >
                    <div className="mb-2 flex items-center justify-between gap-3 text-[11px] font-semibold tracking-wide text-slate-900 dark:text-white/90">
                      <span>DeepSpace status</span>
                      <button
                        type="button"
                        onClick={() => setRuntimeLegendOpen(false)}
                        className="rounded px-1 text-slate-400 hover:text-slate-900 dark:text-white/35 dark:hover:text-white/80"
                        aria-label="Close status legend"
                      >
                        ×
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                      {[
                        ["bg-emerald-400", "Ready / typing"],
                        ["bg-amber-300", "Submitting"],
                        ["bg-cyan-300", "Thinking / receiving"],
                        ["bg-blue-400", "Web/search tool"],
                        ["bg-violet-300", "Reading data"],
                        ["bg-fuchsia-300", "Writing data"],
                        ["bg-slate-500 dark:bg-white", "Completed"],
                        ["bg-red-400", "Error"],
                      ].map(([color, label]) => (
                        <span key={label} className="flex items-center gap-1.5">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${color}`}
                            aria-hidden="true"
                          />
                          {label}
                        </span>
                      ))}
                    </div>
                    <p className="mt-2 border-t border-slate-200 pt-2 text-slate-500 dark:border-white/10 dark:text-white/45">
                      The square button stops a running response; the play button sends your
                      message. Context glow shifts from cyan to amber/red as the model window fills.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <div className="flex flex-shrink-0 items-center gap-2 sm:gap-3">
              {isStreaming && shouldShowActiveResponseControls && !editingQueuedTurnId ? (
                <>
                  <button
                    type="button"
                    onClick={onSteer}
                    disabled={!query.trim()}
                    className="deepspace-composer-steer rounded-lg border border-amber-300/35 bg-amber-300/10 px-2.5 py-2 text-[10px] font-semibold tracking-wide text-amber-100 uppercase transition hover:bg-amber-300/20 disabled:cursor-not-allowed disabled:opacity-40"
                    title="Stop the active response and run this message next"
                  >
                    Steer
                  </button>
                  <motion.button
                    type="button"
                    onClick={onStop}
                    disabled={stopping}
                    aria-label={stopping ? "Stopping response" : "Stop response"}
                    title={
                      stopping ? "Waiting for the server to stop this response" : "Stop response"
                    }
                    className="deepspace-composer-control deepspace-composer-stop flex h-10 w-10 items-center justify-center rounded-xl border border-red-300/45 bg-red-400/10 text-red-100 transition hover:bg-red-400/20 active:scale-95 disabled:cursor-wait disabled:opacity-55"
                    whileTap={{ scale: 0.94 }}
                  >
                    {stopping ? (
                      <span
                        className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
                        aria-hidden="true"
                      />
                    ) : (
                      <StopIcon />
                    )}
                  </motion.button>
                </>
              ) : null}
              <motion.button
                type="button"
                onClick={submitWithAttachments}
                disabled={
                  (!query.trim() && !attachments.some((item) => item.status === "ready")) ||
                  (editingQueuedTurnId !== null && !query.trim()) ||
                  (editingQueuedTurnId !== null && queueAction !== null) ||
                  attachments.some(
                    (item) => item.status === "uploading" || item.status === "processing",
                  )
                }
                aria-label={
                  editingQueuedTurnId
                    ? "Save queued prompt"
                    : isStreaming
                      ? "Queue message"
                      : "Send message"
                }
                title={
                  editingQueuedTurnId
                    ? "Save this prompt and keep its queue position"
                    : isStreaming
                      ? "Queue message"
                      : "Send message"
                }
                className="deepspace-composer-control deepspace-composer-send border-primary/45 from-primary/95 to-primary text-primary-foreground hover:border-primary/70 disabled:border-border-subtle disabled:bg-surface-2 disabled:text-muted-foreground relative flex h-10 w-10 items-center justify-center rounded-xl border bg-gradient-to-br shadow-[0_8px_20px_rgba(var(--primary),0.25)] transition-[border-color,background-color,box-shadow,filter] hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:shadow-none"
                whileHover={{ scale: 1.06 }}
                whileTap={{ scale: 0.94 }}
              >
                <AnimatePresence initial={false} mode="wait">
                  <motion.span
                    key={editingQueuedTurnId ? "save-queue-edit" : isStreaming ? "queue" : "send"}
                    initial={{ opacity: 0, scale: 0.65, rotate: 18 }}
                    animate={{ opacity: 1, scale: 1, rotate: 0 }}
                    exit={{ opacity: 0, scale: 0.65, rotate: -18 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                    className="relative z-10 flex items-center justify-center"
                  >
                    {editingQueuedTurnId ? (
                      <Check className="h-[18px] w-[18px]" strokeWidth={2.5} />
                    ) : (
                      <SendIcon />
                    )}
                  </motion.span>
                </AnimatePresence>
              </motion.button>
            </div>
          </div>
        </div>
      </div>
      {activeAttachmentTooltip
        ? createPortal(
            <span
              id={activeAttachmentTooltip.id}
              role="tooltip"
              className={attachmentTooltipClassName}
              style={{ left: activeAttachmentTooltip.left, top: activeAttachmentTooltip.top }}
            >
              {activeAttachmentTooltip.label}
            </span>,
            document.body,
          )
        : null}
      {attachmentPreview ? (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-md"
          role="dialog"
          aria-modal="true"
          aria-label={`Preview ${attachmentPreview.name}`}
          onClick={() => setAttachmentPreview(null)}
        >
          <div
            className="w-full max-w-2xl rounded-2xl border border-emerald-300/40 bg-white p-4 shadow-2xl dark:bg-slate-950"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-semibold">{attachmentPreview.name}</p>
                <p className="text-xs text-emerald-700">
                  Shared from this composer ·{" "}
                  {attachmentPreview.status === "ready"
                    ? "saved to Library"
                    : attachmentPreview.status}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAttachmentPreview(null)}
                aria-label="Close preview"
              >
                <X size={18} />
              </button>
            </div>
            {attachmentPreview.previewUrl ? (
              <img
                src={attachmentPreview.previewUrl}
                alt={attachmentPreview.name}
                className="max-h-[65vh] w-full rounded-xl object-contain"
              />
            ) : (
              <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-emerald-50 text-emerald-900">
                <FileText size={34} />
                <span className="mt-2 text-sm">Secure Library file preview</span>
                <button
                  type="button"
                  onClick={() => {
                    window.dispatchEvent(
                      new CustomEvent("deepspace-library-open", {
                        detail: { fileId: attachmentPreview.id },
                      }),
                    );
                    setAttachmentPreview(null);
                  }}
                  className="mt-3 rounded-lg border border-emerald-500/40 px-3 py-1 text-xs font-semibold"
                >
                  Open in Library
                </button>
              </div>
            )}
          </div>
        </div>
      ) : null}
      {libraryPickerOpen ? (
        <div
          className="fixed inset-0 z-[210] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-md"
          onClick={() => setLibraryPickerOpen(false)}
        >
          <div
            className="w-full max-w-lg rounded-2xl bg-white p-4 shadow-2xl dark:bg-slate-950"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">Attach from Library</h2>
              <button type="button" onClick={() => setLibraryPickerOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="max-h-80 space-y-1 overflow-auto">
              {libraryFiles.length ? (
                libraryFiles.map((file) => (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => attachLibraryFile(file)}
                    className="flex w-full items-center gap-2 rounded-lg p-2 text-left text-sm hover:bg-emerald-50 dark:hover:bg-emerald-950/30"
                  >
                    <FileText size={16} className="text-emerald-600" />
                    <span className="truncate">{file.name}</span>
                  </button>
                ))
              ) : (
                <p className="text-muted-foreground p-3 text-sm">
                  No files in this Library folder yet.
                </p>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
