"use client";

/* Local object URLs are short-lived, private composer previews; Next image optimization cannot fetch them. */
/* eslint-disable @next/next/no-img-element */

import { AnimatePresence, motion } from "framer-motion";
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
  Volume2,
  VolumeX,
} from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { fetchWithAuth } from "@/lib/api";

type ReasoningEffort = "low" | "medium" | "high" | "very_high" | "extreme_high";

interface DeepSpaceComposerProps {
  conversationId?: string | null;
  query: string;
  isStreaming: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: (attachmentFileIds?: string[]) => void;
  onStop: () => void;
  onSteer?: () => void;
  queuedTurns?: Array<{
    clientRequestId: string;
    prompt: string;
    status: string;
    error?: string | null;
  }>;
  queuePaused?: boolean;
  queuePauseReason?: string | null;
  queueFailedRequestId?: string | null;
  onPauseQueue?: () => void;
  onResumeQueue?: () => void;
  onClearQueue?: () => void;
  onCancelQueuedTurn?: (clientRequestId: string) => void;
  onRetryFailedTurn?: (clientRequestId: string) => void;
  onSteerQueuedTurn?: (clientRequestId: string) => void;
  changedFiles?: Array<{ path: string; additions: number; deletions: number }>;
  modelName?: string | null;
  reasoningEffort?: ReasoningEffort | null;
  onReasoningEffortChange?: (value: ReasoningEffort | null) => void;
  availableModels?: Array<{
    providerId: string;
    modelName: string;
    displayName: string;
    quantization?: string | null;
    contextWindow?: number | null;
    contextWindowSource?: string | null;
    supportedReasoningEfforts?: string[];
  }>;
  onModelSelect?: (providerId: string, modelName: string) => void;
  voiceState?: "idle" | "listening" | "thinking" | "speaking";
  contextUsedTokens?: number | null;
  contextLimit?: number | null;
  contextRemainingTokens?: number | null;
  safeRemainingTokens?: number | null;
  sessionInputTokens?: number | null;
  sessionOutputTokens?: number | null;
  sessionTotalTokens?: number | null;
  requestInputTokens?: number | null;
  requestOutputTokens?: number | null;
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
  cachedInputTokens?: number | null;
  uncachedInputTokens?: number | null;
  providerUsage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    cached_input_tokens?: number | null;
    cache_write_input_tokens?: number | null;
    usage_source?: string;
  } | null;
  tokenCategorySource?: string | null;
  sttActive?: boolean;
  ttsActive?: boolean;
  onSttToggle?: () => void;
  onTtsToggle?: () => void;
  voiceLabel?: string;
  runtimePhase?: DeepSpaceRuntimePhase;
  activeToolName?: string | null;
  hasRuntimeError?: boolean;
}

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

function SendIcon() {
  return <Play className="h-[18px] w-[18px] translate-x-px fill-current" strokeWidth={2.5} />;
}

function StopIcon() {
  return <Square className="h-4 w-4 fill-current" strokeWidth={2.5} />;
}

export default function DeepSpaceComposer({
  conversationId,
  query,
  isStreaming,
  onQueryChange,
  onSubmit,
  onStop,
  onSteer,
  queuedTurns = [],
  queuePaused = false,
  queuePauseReason = null,
  queueFailedRequestId = null,
  onPauseQueue,
  onResumeQueue,
  onClearQueue,
  onCancelQueuedTurn,
  onRetryFailedTurn,
  onSteerQueuedTurn,
  changedFiles = [],
  modelName,
  reasoningEffort = null,
  onReasoningEffortChange,
  availableModels = [],
  onModelSelect,
  voiceState = "idle",
  contextUsedTokens = null,
  contextLimit = null,
  contextRemainingTokens = null,
  safeRemainingTokens = null,
  sessionTotalTokens = null,
  requestInputTokens = null,
  requestOutputTokens = null,
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
  cachedInputTokens = null,
  uncachedInputTokens = null,
  providerUsage = null,
  tokenCategorySource = null,
  sttActive = false,
  ttsActive = false,
  onSttToggle,
  onTtsToggle,
  voiceLabel = "",
  runtimePhase = "idle",
  activeToolName = null,
  hasRuntimeError = false,
}: DeepSpaceComposerProps) {
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [reasoningDropdownOpen, setReasoningDropdownOpen] = useState(false);
  const [runtimeLegendOpen, setRuntimeLegendOpen] = useState(false);
  const [contextDialogOpen, setContextDialogOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [attachmentPreview, setAttachmentPreview] = useState<ComposerAttachment | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const uploadControllersRef = useRef<Record<string, AbortController>>({});
  const [libraryPickerOpen, setLibraryPickerOpen] = useState(false);
  const [libraryFiles, setLibraryFiles] = useState<Array<{ id: string; name: string; content_type: string; size_bytes: number }>>([]);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);


  const importAttachments = async (input: FileList | File[]) => {
    if (!conversationId) return;
    const allFiles = Array.from(input);
    const invalid = allFiles.filter((file) => !file.name || file.size <= 0 || file.size > 25 * 1024 * 1024);
    if (invalid.length) setAttachmentError("Files must have content and be 25 MB or smaller. Unsupported types are safely rejected by Library.");
    const files = allFiles.filter((file) => file.name && file.size > 0 && file.size <= 25 * 1024 * 1024).slice(0, Math.max(0, 10 - attachments.length));
    for (const file of files) {
      const localId = crypto.randomUUID();
      const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
      const controller = new AbortController();
      uploadControllersRef.current[localId] = controller;
      setAttachments((current) => [...current, { id: localId, name: file.name, type: file.type, size: file.size, previewUrl, status: "uploading", loaded: 0, file }]);
      try {
        const created = await fetchWithAuth(`/deepspace/library/${conversationId}/uploads`, {
          method: "POST",
          body: JSON.stringify({ name: file.name, size_bytes: file.size, content_type: file.type || "application/octet-stream" }),
          timeoutMs: 15_000,
        }) as Response;
        if (!created.ok) throw new Error("Library could not accept this file.");
        let upload = await created.json() as { id: string; chunk_size: number; total_chunks: number; received_chunks: number[]; status: string; file_id?: string | null; error?: string | null };
        for (let index = 0; index < upload.total_chunks; index += 1) {
          if (upload.received_chunks.includes(index)) continue;
          const chunk = file.slice(index * upload.chunk_size, Math.min(file.size, (index + 1) * upload.chunk_size));
          const response = await fetchWithAuth(`/deepspace/library/${conversationId}/uploads/${upload.id}/chunks/${index}`, { method: "PUT", body: chunk, signal: controller.signal, timeoutMs: 120_000 }) as Response;
          if (!response.ok) throw new Error("A secure upload chunk was rejected.");
          upload = await response.json();
          setAttachments((current) => current.map((item) => item.id === localId ? { ...item, uploadId: upload.id, loaded: Math.min(file.size, (index + 1) * upload.chunk_size) } : item));
        }
        const complete = await fetchWithAuth(`/deepspace/library/${conversationId}/uploads/${upload.id}/complete`, { method: "POST", timeoutMs: 15_000 }) as Response;
        if (!complete.ok) throw new Error("Library could not process this file.");
        upload = await complete.json();
        setAttachments((current) => current.map((item) => item.id === localId ? { ...item, status: "processing" } : item));
        for (let attempt = 0; attempt < 180 && upload.status !== "completed"; attempt += 1) {
          if (upload.status === "failed" || upload.status === "cancelled") throw new Error(upload.error || "Library processing failed.");
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          const status = await fetchWithAuth(`/deepspace/library/${conversationId}/uploads/${upload.id}`, { timeoutMs: 8_000 }) as Response;
          if (!status.ok) throw new Error("Library upload status is unavailable.");
          upload = await status.json();
        }
        if (upload.status !== "completed" || !upload.file_id) throw new Error("The file is still processing. Please try again shortly.");
        setAttachments((current) => current.map((item) => item.id === localId ? { ...item, id: upload.file_id!, status: "ready" } : item));
        window.dispatchEvent(new CustomEvent("deepspace-library-updated", { detail: { conversationId } }));
      } catch (error) {
        const cancelled = controller.signal.aborted;
        setAttachments((current) => current.map((item) => item.id === localId ? { ...item, status: "error", error: cancelled ? "Upload cancelled." : error instanceof Error ? error.message : "Upload failed." } : item));
      } finally {
        delete uploadControllersRef.current[localId];
      }
    }
  };
  const cancelAttachment = async (item: ComposerAttachment) => {
    uploadControllersRef.current[item.id]?.abort();
    if (item.uploadId && conversationId) await fetchWithAuth(`/deepspace/library/${conversationId}/uploads/${item.uploadId}/cancel`, { method: "POST", timeoutMs: 15_000 });
  };
  const retryAttachment = (item: ComposerAttachment) => {
    removeAttachment(item.id);
    if (item.file) void importAttachments([item.file]);
  };
  const openLibraryPicker = async () => {
    if (!conversationId) return;
    const response = await fetchWithAuth(`/deepspace/library/${conversationId}/entries`, { timeoutMs: 8_000 }) as Response;
    if (response.ok) setLibraryFiles(((await response.json()) as { files: typeof libraryFiles }).files ?? []);
    setLibraryPickerOpen(true);
  };
  const attachLibraryFile = (file: { id: string; name: string; content_type: string; size_bytes: number }) => {
    setAttachments((current) => current.some((item) => item.id === file.id) || current.length >= 10 ? current : [...current, { ...file, type: file.content_type, size: file.size_bytes, status: "ready" }]);
    setLibraryPickerOpen(false);
  };
  const removeAttachment = (id: string) => setAttachments((current) => {
    const removed = current.find((item) => item.id === id);
    if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
    return current.filter((item) => item.id !== id);
  });
  const submitWithAttachments = () => {
    const ready = attachments.filter((item) => item.status === "ready");
    if (attachments.some((item) => item.status === "uploading" || item.status === "processing")) return;
    onSubmit(ready.map((item) => item.id));
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
  const selectedModelMetadata = availableModels.find((model) => model.modelName === modelName);
  const normalizedModelSearch = modelSearch.trim().toLocaleLowerCase();
  const filteredModels = availableModels.filter((model) => {
    if (!normalizedModelSearch) return true;
    return [model.displayName, model.modelName, model.providerId, model.quantization]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase().includes(normalizedModelSearch));
  });
  const advertisedEfforts = (selectedModelMetadata?.supportedReasoningEfforts ?? []).filter(
    (item): item is ReasoningEffort =>
      ["low", "medium", "high", "very_high", "extreme_high"].includes(item),
  );
  const reasoningOptions: Array<ReasoningEffort | null> = advertisedEfforts.length
    ? [null, ...advertisedEfforts]
    : [null, "low", "medium", "high"];
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
              : modelDropdownOpen || contextDialogOpen
                ? "z-[80]"
                : "z-10"
          } ${composerShell} ${shellPadding}`}
        >
          {queuePaused || queuedTurns.length || changedFiles.length ? (
            <div className="mb-2 overflow-hidden rounded-t-xl border border-slate-300/80 bg-white/95 shadow-sm dark:border-cyan-300/20 dark:bg-cyan-950/40">
              {queuePaused || queuedTurns.length ? (
                <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2 text-[11px] dark:border-cyan-300/15">
                  <span className={queuePaused ? "font-semibold text-amber-700 dark:text-amber-200" : "font-semibold text-slate-700 dark:text-cyan-100/75"}>
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
                      className="shrink-0 rounded-md border border-emerald-600/40 bg-emerald-50 px-2 py-1 text-emerald-800 hover:bg-emerald-100 dark:border-emerald-300/25 dark:bg-transparent dark:text-emerald-200/85 dark:hover:bg-emerald-300/10"
                    >
                      {queueFailedRequestId ? "Retry failed & resume" : "Resume queue"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={onPauseQueue}
                      className="shrink-0 rounded-md border border-slate-300 bg-slate-50 px-2 py-1 text-slate-700 hover:bg-slate-100 dark:border-cyan-300/20 dark:bg-transparent dark:text-cyan-100/70 dark:hover:bg-cyan-300/10"
                    >
                      Pause queue
                    </button>
                  )}
                  {queuedTurns.length || queuePaused ? (
                    <button
                      type="button"
                      onClick={onClearQueue}
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
                >
                  {queuedTurns.map((turn, index) => (
                    <div
                      key={turn.clientRequestId}
                      className="flex max-w-full items-center gap-2 rounded-md px-2 py-1.5 text-[11px] text-slate-700 hover:bg-slate-50 dark:text-cyan-100/80 dark:hover:bg-cyan-300/[0.06]"
                    >
                      <span className="text-slate-400 dark:text-cyan-200/60">↳</span>
                      <span className="min-w-0 flex-1 truncate">{turn.prompt}</span>
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
                      {turn.status === "queued" ? (
                        <button
                          type="button"
                          onClick={() => onSteerQueuedTurn?.(turn.clientRequestId)}
                          className="text-slate-600 hover:text-slate-900 dark:text-cyan-100/65 dark:hover:text-cyan-100"
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
                        <span className="max-w-[42%] truncate text-red-700/80 dark:text-red-200/70" title={turn.error}>
                          {turn.error}
                        </span>
                      ) : null}
                      {turn.status === "failed" ? (
                        <button
                          type="button"
                          onClick={() => onRetryFailedTurn?.(turn.clientRequestId)}
                          className="shrink-0 text-amber-700 hover:text-amber-900 dark:text-amber-200/80 dark:hover:text-amber-100"
                        >
                          Retry checkpoint
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          <input ref={fileInputRef} type="file" multiple className="sr-only" onChange={(event) => { if (event.target.files) void importAttachments(event.target.files); event.target.value = ""; }} />
          <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(event) => { if (event.target.files) void importAttachments(event.target.files); event.target.value = ""; }} />
          {attachmentError ? <p className="mb-2 rounded-lg border border-amber-400/40 bg-amber-50 px-2 py-1 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">{attachmentError}<button type="button" className="ml-2 underline" onClick={() => setAttachmentError(null)}>Dismiss</button></p> : null}
          {attachments.length ? (
            <div className="mb-2 flex max-h-28 flex-wrap gap-2 overflow-y-auto px-1" aria-label="Files shared with this message">
              {attachments.map((item) => (
                <div key={item.id} className="group flex w-36 items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-50/80 p-2 text-left text-[10px] text-emerald-950 shadow-sm dark:bg-emerald-950/30 dark:text-emerald-100">
                  <button type="button" onClick={() => setAttachmentPreview(item)} className="flex min-w-0 flex-1 items-center gap-2" title={`Preview ${item.name}`}>
                    {item.previewUrl ? <img src={item.previewUrl} alt="" className="h-9 w-9 rounded object-cover" /> : <FileText className="h-5 w-5 shrink-0 text-emerald-600" />}
                    <span className="min-w-0"><span className="block truncate font-semibold">{item.name}</span><span className="block text-emerald-700/70">{item.status === "ready" ? "Saved to Library" : item.status === "error" ? item.error : item.status === "processing" ? "Scanning…" : `Uploading ${Math.round(((item.loaded ?? 0) / Math.max(1, item.size)) * 100)}%`}</span></span>
                  </button>
                  {item.status === "error" && item.file ? <button type="button" onClick={() => retryAttachment(item)} className="shrink-0 text-emerald-700 hover:text-emerald-900" aria-label={`Retry ${item.name}`}><RotateCw size={13} /></button> : null}
                  {item.status === "uploading" || item.status === "processing" ? <button type="button" onClick={() => void cancelAttachment(item)} className="shrink-0 text-amber-700 hover:text-rose-600" aria-label={`Cancel ${item.name}`}><X size={13} /></button> : <button type="button" onClick={() => removeAttachment(item.id)} className="shrink-0 text-emerald-700 hover:text-rose-600" aria-label={`Remove ${item.name}`}><X size={13} /></button>}
                </div>
              ))}
            </div>
          ) : null}
          <div className="flex items-start gap-2">
          <div className="deepspace-attachment-actions flex shrink-0 gap-1.5">
          <button type="button" onClick={() => fileInputRef.current?.click()} disabled={!conversationId} className="deepspace-attachment-action ui-tooltip ui-tooltip-top" data-tooltip="Attach files or paste a screenshot" aria-label="Attach files from your device"><Paperclip size={16} /></button>
          <button type="button" onClick={() => cameraInputRef.current?.click()} disabled={!conversationId} className="deepspace-attachment-action ui-tooltip ui-tooltip-top" data-tooltip="Take a photo" aria-label="Take a photo"><Camera size={16} /></button>
          <button type="button" onClick={() => void openLibraryPicker()} disabled={!conversationId} className="deepspace-attachment-action ui-tooltip ui-tooltip-top" data-tooltip="Attach from Library" aria-label="Attach an existing Library file"><FolderOpen size={16} /></button>
          </div>
          <textarea
            value={query}
            onChange={(event) => onQueryChange(event.target.value.slice(0, 4000))}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submitWithAttachments();
              }
            }}
            placeholder="Message DeepSpace..."
            onPaste={(event) => { const files = Array.from(event.clipboardData.files); if (files.length) { event.preventDefault(); void importAttachments(files); } }}
            onDrop={(event) => { const files = Array.from(event.dataTransfer.files); if (files.length) { event.preventDefault(); void importAttachments(files); } }}
            onDragOver={(event) => event.preventDefault()}
            className={`text-foreground placeholder:text-foreground/30 w-full resize-none border-none bg-transparent outline-none ${textareaClass}`}
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
              <span className="deepspace-context-values shrink-0 tabular-nums">
                {(contextUsedTokens ?? 0).toLocaleString()} /{" "}
                {hasContextLimit ? contextLimit?.toLocaleString() : "—"} ·{" "}
                {(requestInputTokens ?? 0).toLocaleString()} model in ·{" "}
                {(requestOutputTokens ?? 0).toLocaleString()} model out ·{" "}
                {hasContextLimit ? `${Math.round(contextRatio * 100)}%` : "—"}
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
                        Current request context
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
                        Model input estimate
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(requestInputTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--output rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Model output estimate
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
                        Session processed
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(sessionTotalTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="deepspace-diagnostics-metric deepspace-diagnostics-metric--reserve rounded-xl border p-2.5">
                      <span className="deepspace-diagnostics-metric-label text-muted-foreground block">
                        Output reserve
                      </span>
                      <strong className="deepspace-diagnostics-metric-value text-foreground">
                        {(reservedOutputTokens ?? maxOutputTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                  </div>
                  <p className="deepspace-diagnostics-description border-border text-muted-foreground mt-3 border-t pt-3">
                    This is an estimate for the latest serialized model request. It can change when
                    the prompt, history, selected tools, or retrieved evidence changes. Model input
                    includes hidden instructions and selected context; it is separate from the
                    visible conversation meter.
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Conversation: {(conversationVisibleTokens ?? 0).toLocaleString()} tokens ·{" "}
                    {(userVisibleInputTokens ?? 0).toLocaleString()} in ·{" "}
                    {(userVisibleOutputTokens ?? 0).toLocaleString()} out
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Categories: system {systemContextTokens?.toLocaleString() ?? "—"} · schemas{" "}
                    {toolSchemaTokens?.toLocaleString() ?? "—"} · results{" "}
                    {toolResultTokens?.toLocaleString() ?? "—"} · cached{" "}
                    {cachedInputTokens?.toLocaleString() ?? "unknown"} · uncached{" "}
                    {uncachedInputTokens?.toLocaleString() ?? "—"}
                    {providerUsage?.usage_source === "provider"
                      ? ` · provider input ${providerUsage.input_tokens?.toLocaleString() ?? "—"} · output ${providerUsage.output_tokens?.toLocaleString() ?? "—"} · cache read ${providerUsage.cached_input_tokens?.toLocaleString() ?? "0"} · cache write ${providerUsage.cache_write_input_tokens?.toLocaleString() ?? "0"}`
                      : ""}
                  </p>
                  <p className="text-muted-foreground mt-1">
                    Adaptive budgets: history {adaptiveHistoryBudgetTokens?.toLocaleString() ?? "—"}{" "}
                    · tool results {adaptiveToolResultBudgetTokens?.toLocaleString() ?? "—"}
                  </p>
                  {tokenCategorySource ? (
                    <p className="text-muted-foreground mt-1 text-[9px]">
                      Source: {tokenCategorySource}
                    </p>
                  ) : null}
                  <p className="text-muted-foreground mt-1">
                    Prompt cache:{" "}
                    {promptCacheStatus === "native_requested"
                      ? `${promptCacheMode} requested (provider status unavailable)`
                      : promptCacheStatus === "unsupported"
                        ? "provider-native caching unavailable"
                        : promptCacheStatus === "disabled"
                          ? "disabled"
                          : promptCacheEligible
                            ? `${promptCacheMode} eligible`
                            : "status unavailable"}
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
                      className="deepspace-model-menu absolute bottom-full left-0 z-[100] mb-2 flex max-h-[22rem] min-w-[min(19rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border p-1"
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
                          className="deepspace-model-menu-search h-8 w-full rounded-lg border px-2.5 text-xs outline-none"
                        />
                      </div>
                      {filteredModels.length > 0 ? (
                        <div className="deepspace-model-menu-list min-h-0 overflow-y-auto p-1">
                          {filteredModels.map((m) => {
                            const selected = m.modelName === modelName;
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
                  {reasoningEffort
                    ? reasoningEffort[0].toUpperCase() + reasoningEffort.slice(1)
                    : "Off"}
                  <ChevronDown size={11} className={reasoningDropdownOpen ? "rotate-180" : ""} />
                </button>
                <AnimatePresence>
                  {reasoningDropdownOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 4 }}
                      className="border-glass-border bg-surface-1 absolute bottom-full left-0 z-[70] mb-2 min-w-[150px] rounded-xl border p-1 shadow-[0_16px_40px_rgba(0,0,0,0.45)]"
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
                          {effort ? effort[0].toUpperCase() + effort.slice(1) : "Off"}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Direct Voice Integration Controls */}
              <div className="relative flex h-8 items-center rounded-lg border border-white/10 bg-black/40 p-0.5 backdrop-blur-md">
                {/* Voice Dictation (STT Mode) Button */}
                <div className="group relative">
                  <button
                    type="button"
                    onClick={onSttToggle}
                    className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                      sttActive
                        ? "border border-emerald-500/35 bg-emerald-500/25 text-emerald-400 shadow-[0_2px_8px_rgba(16,185,129,0.3)]"
                        : "border border-transparent text-white/40 hover:text-white/80"
                    }`}
                    aria-label="Voice Dictation (STT)"
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
                      Voice Dictation (STT)
                    </div>
                  </div>
                </div>

                {/* Jarvis Mode (Verbal Commentary) Button */}
                <div className="group relative">
                  <button
                    type="button"
                    onClick={onTtsToggle}
                    className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                      ttsActive
                        ? "bg-primary/20 text-primary border-primary/35 border shadow-[0_2px_8px_rgba(var(--primary),0.3)]"
                        : "border border-transparent text-white/40 hover:text-white/80"
                    }`}
                    aria-label="Jarvis Mode"
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
                      Voice Commentary (TTS)
                    </div>
                  </div>
                </div>
              </div>

              {(sttActive || ttsActive) && voiceLabel && (
                <span className="ml-0.5 max-w-[140px] animate-pulse truncate text-[10px] font-semibold tracking-wide text-white/45">
                  {voiceLabel}
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
                    className="border-slate-200 bg-white/95 text-slate-600 absolute right-0 bottom-full isolate z-[70] mb-2 w-[min(19rem,calc(100vw-2rem))] rounded-xl border p-3 text-[10px] leading-4 shadow-2xl ring-1 ring-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-[#0b1411]/95 dark:text-white/65 dark:ring-black/50"
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
              {isStreaming ? (
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
                    aria-label="Stop response"
                    title="Stop response"
                    className="deepspace-composer-control deepspace-composer-stop flex h-10 w-10 items-center justify-center rounded-xl border border-red-300/45 bg-red-400/10 text-red-100 transition hover:bg-red-400/20 active:scale-95"
                    whileTap={{ scale: 0.94 }}
                  >
                    <StopIcon />
                  </motion.button>
                </>
              ) : null}
              <motion.button
                type="button"
                onClick={submitWithAttachments}
                disabled={(!query.trim() && !attachments.some((item) => item.status === "ready")) || attachments.some((item) => item.status === "uploading" || item.status === "processing")}
                aria-label={isStreaming ? "Queue message" : "Send message"}
                title={isStreaming ? "Queue message" : "Send message"}
                className="deepspace-composer-control deepspace-composer-send border-primary/45 from-primary/95 to-primary text-primary-foreground hover:border-primary/70 disabled:border-border-subtle disabled:bg-surface-2 disabled:text-muted-foreground relative flex h-10 w-10 items-center justify-center rounded-xl border bg-gradient-to-br shadow-[0_8px_20px_rgba(var(--primary),0.25)] transition-[border-color,background-color,box-shadow,filter] hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:shadow-none"
                whileHover={{ scale: 1.06 }}
                whileTap={{ scale: 0.94 }}
              >
                <AnimatePresence initial={false} mode="wait">
                  <motion.span
                    key={isStreaming ? "queue" : "send"}
                    initial={{ opacity: 0, scale: 0.65, rotate: 18 }}
                    animate={{ opacity: 1, scale: 1, rotate: 0 }}
                    exit={{ opacity: 0, scale: 0.65, rotate: -18 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                    className="relative z-10 flex items-center justify-center"
                  >
                    <SendIcon />
                  </motion.span>
                </AnimatePresence>
              </motion.button>
            </div>
          </div>
        </div>
      </div>
      {attachmentPreview ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-md" role="dialog" aria-modal="true" aria-label={`Preview ${attachmentPreview.name}`} onClick={() => setAttachmentPreview(null)}>
          <div className="w-full max-w-2xl rounded-2xl border border-emerald-300/40 bg-white p-4 shadow-2xl dark:bg-slate-950" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate font-semibold">{attachmentPreview.name}</p><p className="text-xs text-emerald-700">Shared from this composer · {attachmentPreview.status === "ready" ? "saved to Library" : attachmentPreview.status}</p></div><button type="button" onClick={() => setAttachmentPreview(null)} aria-label="Close preview"><X size={18} /></button></div>
            {attachmentPreview.previewUrl ? <img src={attachmentPreview.previewUrl} alt={attachmentPreview.name} className="max-h-[65vh] w-full rounded-xl object-contain" /> : <div className="flex h-48 flex-col items-center justify-center rounded-xl bg-emerald-50 text-emerald-900"><FileText size={34} /><span className="mt-2 text-sm">Secure Library file preview</span><button type="button" onClick={() => { window.dispatchEvent(new CustomEvent("deepspace-library-open", { detail: { fileId: attachmentPreview.id } })); setAttachmentPreview(null); }} className="mt-3 rounded-lg border border-emerald-500/40 px-3 py-1 text-xs font-semibold">Open in Library</button></div>}
          </div>
        </div>
      ) : null}
      {libraryPickerOpen ? <div className="fixed inset-0 z-[210] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-md" onClick={() => setLibraryPickerOpen(false)}><div className="w-full max-w-lg rounded-2xl bg-white p-4 shadow-2xl dark:bg-slate-950" onClick={(event) => event.stopPropagation()}><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Attach from Library</h2><button type="button" onClick={() => setLibraryPickerOpen(false)}><X size={18} /></button></div><div className="max-h-80 space-y-1 overflow-auto">{libraryFiles.length ? libraryFiles.map((file) => <button key={file.id} type="button" onClick={() => attachLibraryFile(file)} className="flex w-full items-center gap-2 rounded-lg p-2 text-left text-sm hover:bg-emerald-50 dark:hover:bg-emerald-950/30"><FileText size={16} className="text-emerald-600" /><span className="truncate">{file.name}</span></button>) : <p className="p-3 text-sm text-muted-foreground">No files in this Library folder yet.</p>}</div></div></div> : null}
    </div>
  );
}
