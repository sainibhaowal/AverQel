"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle,
  ArrowUp,
  Bot,
  Check,
  ChevronDown,
  CircleCheck,
  FolderOpen,
  LoaderCircle,
  ListPlus,
  Pause,
  Play,
  Paperclip,
  Search,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import ProviderLogo from "@/app/components/providers/ProviderLogo";
import { fetchWithAuth } from "@/lib/api";
import { MAX_QUERY_ATTACHMENTS } from "../_lib/query-limits";

export interface QueryComposerAttachment {
  id: string;
  documentId?: string;
  name: string;
  status: "queued" | "uploading" | "processing" | "ready" | "failed";
  error?: string;
  progress?: number;
  stage?: string;
  rowCount?: number;
}

interface HubAttachmentOption {
  document_id: string;
  filename: string;
  size_bytes: number;
  tabular: boolean;
}

export interface QueryComposerQueueItem {
  id: string;
  query: string;
  attachments: Array<{ id: string; name: string }>;
  status?: "queued" | "failed";
}

interface QueryComposerProps {
  query: string;
  searchMode: "hybrid" | "semantic" | "keyword";
  selectedCollectionId: string;
  collectionOptions: Array<{ id: string; name: string }>;
  collectionScopeLoading: boolean;
  isStreaming: boolean;
  requestPending?: boolean;
  filtersOpen: boolean;
  supportsThinking: boolean;
  thinkingEnabled: boolean;
  onQueryChange: (value: string) => void;
  onSearchModeChange: (value: "hybrid" | "semantic" | "keyword") => void;
  onCollectionChange: (value: string) => void;
  onToggleFilters: () => void;
  onThinkingChange: (value: boolean) => void;
  onSubmit: (attachments: QueryComposerAttachment[]) => void;
  onStop: () => void;
  modelName?: string | null;
  selectedProviderId?: string | null;
  availableModels?: Array<{
    providerId: string;
    providerName?: string;
    providerType?: string;
    modelName: string;
    displayName: string;
    quantization?: string | null;
    contextWindow?: number | null;
    contextWindowSource?: string | null;
  }>;
  onModelSelect?: (providerId: string, modelName: string) => void;
  contextUsedTokens?: number | null;
  contextLimit?: number | null;
  attachments?: QueryComposerAttachment[];
  onFilesSelected?: (files: FileList | null) => void;
  onExistingDocumentSelect?: (document: HubAttachmentOption) => void;
  onRemoveAttachment?: (id: string) => void;
  onRetryAttachment?: (id: string) => void;
  queueItems?: QueryComposerQueueItem[];
  queuePaused?: boolean;
  onToggleQueuePaused?: () => void;
  onRetryQueueItem?: (id: string) => void;
  onRemoveQueueItem?: (id: string) => void;
  onClearQueue?: () => void;
}

const MODEL_SEARCH_FIELDS = (model: NonNullable<QueryComposerProps["availableModels"]>[number]) =>
  [
    model.displayName,
    model.modelName,
    model.providerName,
    model.providerType,
    model.providerId,
    model.quantization,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();

export const MAX_QUERY_QUEUE_ITEMS = 20;

export default function QueryComposer({
  query,
  searchMode,
  isStreaming,
  requestPending = false,
  supportsThinking,
  thinkingEnabled,
  onQueryChange,
  onThinkingChange,
  onSubmit,
  onStop,
  modelName,
  selectedProviderId,
  availableModels = [],
  onModelSelect,
  contextUsedTokens = null,
  contextLimit = null,
  attachments = [],
  onFilesSelected = () => {},
  onExistingDocumentSelect = () => {},
  onRemoveAttachment = () => {},
  onRetryAttachment = () => {},
  queueItems = [],
  queuePaused = false,
  onToggleQueuePaused = () => {},
  onRetryQueueItem = () => {},
  onRemoveQueueItem = () => {},
  onClearQueue = () => {},
}: QueryComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [expandedProviderId, setExpandedProviderId] = useState<string | null>(null);
  const [queueExpanded, setQueueExpanded] = useState(false);
  const [hubPickerOpen, setHubPickerOpen] = useState(false);
  const [hubSearch, setHubSearch] = useState("");
  const [hubSkip, setHubSkip] = useState(0);
  const [hubDocuments, setHubDocuments] = useState<HubAttachmentOption[]>([]);
  const [hubTotal, setHubTotal] = useState(0);
  const [hubLoading, setHubLoading] = useState(false);
  const [hubError, setHubError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const modelTriggerRef = useRef<HTMLButtonElement | null>(null);
  const modelSearchRef = useRef<HTMLInputElement | null>(null);

  const filteredModels = useMemo(() => {
    const search = modelSearch.trim().toLocaleLowerCase();
    const sorted = [...availableModels].sort((left, right) => {
      const providerOrder = (left.providerName || left.providerId).localeCompare(
        right.providerName || right.providerId,
      );
      return providerOrder || left.displayName.localeCompare(right.displayName);
    });
    return search ? sorted.filter((model) => MODEL_SEARCH_FIELDS(model).includes(search)) : sorted;
  }, [availableModels, modelSearch]);

  const modelGroups = useMemo(() => {
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
      const providerName = model.providerName?.trim() || model.providerType || "Provider";
      const current = groups.get(model.providerId);
      if (current) current.models.push(model);
      else
        groups.set(model.providerId, {
          providerId: model.providerId,
          providerName,
          providerType: model.providerType,
          models: [model],
        });
    }
    return [...groups.values()];
  }, [filteredModels]);

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  useEffect(() => {
    if (!hubPickerOpen) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setHubLoading(true);
      setHubError(null);
      const params = new URLSearchParams({ skip: String(hubSkip), limit: "50" });
      if (hubSearch.trim()) params.set("q", hubSearch.trim());
      void (async () => {
        try {
          const response = (await fetchWithAuth(`/queries/attachments?${params}`, {
            signal: controller.signal,
            timeoutMs: 20_000,
          })) as Response;
          if (!response.ok)
            throw new Error(`Documents Hub search failed (HTTP ${response.status}).`);
          const payload = (await response.json()) as {
            items?: HubAttachmentOption[];
            total?: number;
          };
          setHubDocuments((current) =>
            hubSkip === 0 ? payload.items || [] : [...current, ...(payload.items || [])],
          );
          setHubTotal(payload.total || 0);
        } catch (error) {
          if (!controller.signal.aborted) {
            setHubError(error instanceof Error ? error.message : "Could not search Documents Hub.");
          }
        } finally {
          if (!controller.signal.aborted) setHubLoading(false);
        }
      })();
    }, 200);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [hubPickerOpen, hubSearch, hubSkip]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const lineHeight = Number.parseFloat(window.getComputedStyle(textarea).lineHeight) || 24;
    const maximumHeight = lineHeight * 4 + 20;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maximumHeight)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maximumHeight ? "auto" : "hidden";
  }, [query]);

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.currentTarget.files;
    onFilesSelected(files);
    event.currentTarget.value = "";
  };

  const readyAttachments = attachments.filter((attachment) => attachment.status === "ready");
  const attachmentsBusy = attachments.some(
    (attachment) =>
      attachment.status === "queued" ||
      attachment.status === "uploading" ||
      attachment.status === "processing",
  );
  const attachmentCounts = attachments.reduce(
    (counts, attachment) => {
      counts[attachment.status] += 1;
      return counts;
    },
    { queued: 0, uploading: 0, processing: 0, ready: 0, failed: 0 },
  );
  const requestActive = isStreaming || requestPending;
  const queueFull =
    (requestActive || queuePaused || queueItems.length > 0) &&
    queueItems.length >= MAX_QUERY_QUEUE_ITEMS;
  const canSubmit =
    Boolean(query.trim()) &&
    !attachmentsBusy &&
    readyAttachments.length === attachments.length &&
    !queueFull;
  const modelSelectionLocked = requestActive || queueItems.length > 0 || queuePaused;

  return (
    <div className="query-composer-scope border-glass-border/60 sticky bottom-0 z-20 border-t bg-transparent px-2 pt-3 pb-0 sm:px-5">
      <div className="border-primary/30 bg-surface-1/35 relative mx-auto w-full max-w-5xl overflow-visible rounded-2xl border p-2.5 shadow-lg backdrop-blur-md transition-all duration-300 sm:p-3">
        {attachments.length > 0 ? (
          <div className="mb-2 space-y-2 px-1" aria-label="Attached documents" aria-live="polite">
            <div className="border-primary/20 bg-primary/[0.06] flex flex-col gap-1 rounded-lg border px-3 py-2 text-xs sm:flex-row sm:items-center sm:justify-between sm:gap-3">
              <div className="flex min-w-0 items-center gap-2">
                {attachmentsBusy ? (
                  <LoaderCircle
                    size={14}
                    className="text-primary shrink-0 animate-spin"
                    aria-hidden="true"
                  />
                ) : attachmentCounts.failed > 0 ? (
                  <AlertCircle size={14} className="text-danger shrink-0" aria-hidden="true" />
                ) : (
                  <CircleCheck size={14} className="shrink-0 text-emerald-500" aria-hidden="true" />
                )}
                <span className="text-foreground/80 min-w-0 truncate font-medium">
                  {attachmentCounts.uploading > 0
                    ? "Uploading to Documents Hub"
                    : attachmentCounts.queued > 0
                      ? "Waiting to upload"
                      : attachmentCounts.processing > 0
                        ? "Indexing in Documents Hub"
                        : attachmentCounts.failed > 0
                          ? "Some files need attention"
                          : "Files are ready to query"}
                </span>
              </div>
              <span className="text-foreground/55 pl-6 text-[10px] tabular-nums sm:shrink-0 sm:pl-0">
                {attachmentCounts.ready}/{attachments.length} ready
                {attachmentCounts.uploading > 0 ? ` · ${attachmentCounts.uploading} uploading` : ""}
                {attachmentCounts.queued > 0 ? ` · ${attachmentCounts.queued} waiting` : ""}
                {attachmentCounts.processing > 0
                  ? ` · ${attachmentCounts.processing} indexing`
                  : ""}
              </span>
            </div>
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                className="border-glass-border bg-surface-0/60 text-foreground/75 flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px]"
                title={attachment.error || attachment.name}
              >
                {attachment.status === "queued" ||
                attachment.status === "uploading" ||
                attachment.status === "processing" ? (
                  <LoaderCircle
                    size={12}
                    className="text-primary shrink-0 animate-spin"
                    aria-hidden="true"
                  />
                ) : attachment.status === "ready" ? (
                  <CircleCheck size={12} className="shrink-0 text-emerald-500" aria-hidden="true" />
                ) : (
                  <AlertCircle size={12} className="text-danger shrink-0" aria-hidden="true" />
                )}
                <span className="max-w-48 truncate">{attachment.name}</span>
                <span className="text-foreground/45 shrink-0">
                  {attachment.status === "queued"
                    ? "Waiting to upload"
                    : attachment.status === "uploading"
                      ? "Uploading to Documents Hub"
                      : attachment.status === "processing"
                        ? attachment.progress !== undefined
                          ? `Indexing table · ${attachment.stage?.replace(/_/g, " ") || "processing"} · ${attachment.progress}%${attachment.rowCount !== undefined ? ` · ${attachment.rowCount.toLocaleString()} rows` : ""}`
                          : "Indexing in Documents Hub"
                        : attachment.status === "ready"
                          ? "Ready to query"
                          : "Failed"}
                </span>
                {attachment.status === "failed" && attachment.documentId ? (
                  <button
                    type="button"
                    onClick={() => onRetryAttachment(attachment.id)}
                    className="text-primary hover:text-primary/80 shrink-0 underline underline-offset-2"
                  >
                    Check again
                  </button>
                ) : null}
                <button
                  type="button"
                  aria-label={`Remove ${attachment.name} from this query`}
                  onClick={() => onRemoveAttachment(attachment.id)}
                  className="text-foreground/45 hover:text-foreground ml-0.5 rounded p-0.5"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
            {attachments
              .filter((attachment) => attachment.status === "failed" && attachment.error)
              .map((attachment) => (
                <p
                  key={`${attachment.id}-error`}
                  className="text-danger w-full px-1 text-[10px]"
                  role="status"
                >
                  {attachment.name}: {attachment.error}
                </p>
              ))}
          </div>
        ) : null}

        <textarea
          ref={textareaRef}
          value={query}
          onChange={(event) => onQueryChange(event.target.value.slice(0, 4000))}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (canSubmit) onSubmit(readyAttachments);
            }
          }}
          placeholder="Ask a question about your documents..."
          aria-label="Ask a grounded query"
          className="text-foreground placeholder:text-foreground/40 max-h-[7rem] min-h-[4.5rem] w-full resize-none border-none bg-transparent px-2.5 py-2 text-[15px] leading-6 outline-none sm:px-3"
        />

        {queueItems.length > 0 ? (
          <div className="border-glass-border/70 mt-2 overflow-hidden rounded-xl border">
            <div className="flex items-center justify-between gap-2 px-2.5 py-2">
              <button
                type="button"
                aria-expanded={queueExpanded}
                onClick={() => setQueueExpanded((value) => !value)}
                className="text-foreground/70 hover:text-foreground flex min-w-0 items-center gap-1.5 text-xs font-medium"
              >
                <ListPlus size={14} className="text-primary shrink-0" />
                <span>
                  {queueItems.length} queued {queueItems.length === 1 ? "query" : "queries"}
                </span>
                <ChevronDown
                  size={13}
                  className={`transition-transform ${queueExpanded ? "rotate-180" : ""}`}
                />
              </button>
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="text-foreground/45 hidden text-[10px] sm:inline">
                  {queuePaused
                    ? "Paused"
                    : requestActive
                      ? "Next after current"
                      : "Waiting to send"}
                </span>
                <button
                  type="button"
                  onClick={onToggleQueuePaused}
                  aria-label={queuePaused ? "Resume query queue" : "Pause query queue"}
                  className="border-glass-border text-foreground/70 hover:text-foreground rounded-md border p-1.5"
                >
                  {queuePaused ? <Play size={12} /> : <Pause size={12} />}
                </button>
                <button
                  type="button"
                  onClick={onClearQueue}
                  aria-label="Clear queued queries"
                  className="border-glass-border text-foreground/70 hover:text-danger rounded-md border p-1.5"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            <AnimatePresence initial={false}>
              {queueExpanded ? (
                <motion.ol
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="border-glass-border divide-glass-border max-h-36 divide-y overflow-y-auto border-t"
                  aria-label="Queued queries"
                >
                  {queueItems.map((item, index) => (
                    <li key={item.id} className="flex items-start gap-2 px-2.5 py-2 text-xs">
                      <span className="text-foreground/40 mt-0.5 shrink-0 tabular-nums">
                        {index + 1}.
                      </span>
                      <span
                        className={`min-w-0 flex-1 truncate ${item.status === "failed" ? "text-danger" : "text-foreground/75"}`}
                        title={item.query}
                      >
                        {item.query}
                        {item.attachments.length ? (
                          <span className="text-foreground/45 ml-1">
                            · {item.attachments.length}{" "}
                            {item.attachments.length === 1 ? "file" : "files"}
                          </span>
                        ) : null}
                      </span>
                      {item.status === "failed" ? (
                        <button
                          type="button"
                          aria-label={`Retry queued query ${index + 1}`}
                          onClick={() => onRetryQueueItem(item.id)}
                          className="text-primary hover:text-primary/80 shrink-0 rounded px-1 py-0.5 text-[10px] font-medium"
                        >
                          Retry
                        </button>
                      ) : null}
                      <button
                        type="button"
                        aria-label={`Remove queued query ${index + 1}`}
                        onClick={() => onRemoveQueueItem(item.id)}
                        className="text-foreground/45 hover:text-danger shrink-0 rounded p-0.5"
                      >
                        <X size={13} />
                      </button>
                    </li>
                  ))}
                </motion.ol>
              ) : null}
            </AnimatePresence>
          </div>
        ) : null}

        {contextLimit && contextLimit > 0 ? (
          <div className="mt-1 flex items-center gap-2 px-2 text-[9px] text-white/50">
            <span className="shrink-0 tracking-[0.14em] uppercase">Context</span>
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                className={`h-full rounded-full transition-[width] duration-200 ${
                  (contextUsedTokens ?? 0) / contextLimit > 0.9
                    ? "bg-red-400"
                    : (contextUsedTokens ?? 0) / contextLimit > 0.7
                      ? "bg-amber-300"
                      : "bg-cyan-300"
                }`}
                style={{
                  width: `${Math.min(100, Math.max(0, ((contextUsedTokens ?? 0) / contextLimit) * 100))}%`,
                }}
              />
            </div>
            <span className="shrink-0 tabular-nums">
              {(contextUsedTokens ?? 0).toLocaleString()} / {contextLimit.toLocaleString()}
            </span>
          </div>
        ) : null}

        <div className="border-glass-border mt-3 flex items-center justify-between gap-2 border-t pt-3">
          <div className="flex min-w-0 flex-grow flex-wrap items-center gap-1.5 sm:gap-2">
            <div ref={dropdownRef} className="relative flex-shrink-0">
              <button
                ref={modelTriggerRef}
                type="button"
                aria-haspopup="dialog"
                aria-controls="query-model-menu"
                aria-expanded={modelDropdownOpen}
                onClick={() => {
                  if (modelDropdownOpen) {
                    setModelDropdownOpen(false);
                    return;
                  }
                  setModelSearch("");
                  const selectedModel = availableModels.find(
                    (model) =>
                      model.modelName === modelName &&
                      (!selectedProviderId || selectedProviderId === model.providerId),
                  );
                  setExpandedProviderId(
                    selectedProviderId ||
                      selectedModel?.providerId ||
                      modelGroups[0]?.providerId ||
                      null,
                  );
                  setModelDropdownOpen(true);
                  requestAnimationFrame(() => modelSearchRef.current?.focus());
                }}
                disabled={modelSelectionLocked}
                className="theme-pill hover:text-foreground flex cursor-pointer items-center gap-1.5 !rounded-lg transition-all hover:bg-white/5 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Bot size={12} />
                <span className="max-w-[10rem] truncate">{modelName || "Select Model"}</span>
                <ChevronDown
                  size={12}
                  className={`transition-transform duration-200 ${modelDropdownOpen ? "rotate-180" : ""}`}
                />
              </button>

              <AnimatePresence>
                {modelDropdownOpen ? (
                  <motion.div
                    id="query-model-menu"
                    role="dialog"
                    aria-label="Choose a model"
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.98 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                    className="border-glass-border bg-surface-0/95 absolute bottom-full left-0 z-50 mb-2 flex max-h-[min(26rem,70vh)] w-[min(22rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border shadow-2xl backdrop-blur-xl"
                  >
                    <label className="border-glass-border flex shrink-0 items-center gap-2 border-b px-3 py-2">
                      <Search size={14} className="text-foreground/45 shrink-0" />
                      <input
                        ref={modelSearchRef}
                        type="search"
                        aria-label="Search models"
                        placeholder="Search providers and models..."
                        value={modelSearch}
                        onChange={(event) => setModelSearch(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Escape") {
                            setModelDropdownOpen(false);
                            modelTriggerRef.current?.focus();
                          }
                        }}
                        className="text-foreground placeholder:text-foreground/40 min-w-0 flex-1 !rounded-none !border-0 !bg-transparent p-0 text-xs !shadow-none outline-none focus:!border-0 focus:!ring-0"
                      />
                      {modelSearch ? (
                        <button
                          type="button"
                          aria-label="Clear model search"
                          onClick={() => setModelSearch("")}
                          className="text-foreground/45 hover:text-foreground rounded p-0.5"
                        >
                          <X size={12} />
                        </button>
                      ) : null}
                    </label>
                    <div className="custom-scrollbar min-h-0 overflow-y-auto p-1.5">
                      {modelGroups.length > 0 ? (
                        modelGroups.map((group) => {
                          const expanded = expandedProviderId === group.providerId;
                          const groupId = `query-model-provider-${group.providerId}`;
                          return (
                            <section key={group.providerId} className="mb-1 last:mb-0">
                              <button
                                type="button"
                                aria-expanded={expanded}
                                aria-controls={expanded ? groupId : undefined}
                                onClick={() =>
                                  setExpandedProviderId(expanded ? null : group.providerId)
                                }
                                className="border-glass-border/70 hover:bg-foreground/[0.04] flex w-full items-center gap-2 rounded-lg border px-2 py-2 text-left transition-colors"
                              >
                                <span
                                  aria-hidden="true"
                                  className="flex h-7 w-7 shrink-0 items-center justify-center"
                                >
                                  <ProviderLogo providerType={group.providerType} size={22} />
                                </span>
                                <span className="flex min-w-0 flex-1 flex-col">
                                  <span className="text-foreground/85 truncate text-xs font-semibold">
                                    {group.providerName}
                                  </span>
                                  {group.providerType ? (
                                    <span className="text-foreground/45 truncate text-[9px] tracking-wide uppercase">
                                      {group.providerType.replaceAll("_", " ")}
                                    </span>
                                  ) : null}
                                </span>
                                <span className="text-foreground/50 shrink-0 text-[10px] tabular-nums">
                                  {group.models.length}
                                </span>
                                <ChevronDown
                                  size={12}
                                  aria-hidden="true"
                                  className={`text-foreground/50 shrink-0 transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
                                />
                              </button>
                              {expanded ? (
                                <div
                                  id={groupId}
                                  role="group"
                                  aria-label={`${group.providerName} models`}
                                  className="space-y-0.5 pt-1 pb-1 pl-2"
                                >
                                  {group.models.map((model) => {
                                    const selected =
                                      model.modelName === modelName &&
                                      (!selectedProviderId ||
                                        selectedProviderId === model.providerId);
                                    return (
                                      <button
                                        key={`${model.providerId}-${model.modelName}`}
                                        type="button"
                                        aria-pressed={selected}
                                        onClick={() => {
                                          onModelSelect?.(model.providerId, model.modelName);
                                          setModelDropdownOpen(false);
                                          modelTriggerRef.current?.focus();
                                        }}
                                        className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${
                                          selected
                                            ? "bg-primary/15 text-primary font-medium"
                                            : "text-foreground/80 hover:bg-foreground/[0.05]"
                                        }`}
                                      >
                                        <span className="flex min-w-0 items-center gap-1.5">
                                          <span className="truncate">{model.displayName}</span>
                                          {model.quantization ? (
                                            <span className="text-primary/70 shrink-0 text-[9px] font-semibold tracking-wide uppercase">
                                              {model.quantization}
                                            </span>
                                          ) : null}
                                        </span>
                                        {selected ? (
                                          <Check size={12} className="ml-1 shrink-0" />
                                        ) : null}
                                      </button>
                                    );
                                  })}
                                </div>
                              ) : null}
                            </section>
                          );
                        })
                      ) : (
                        <div className="text-foreground/50 flex items-center gap-2 px-2.5 py-4 text-xs">
                          <Search size={13} />
                          No matching models
                        </div>
                      )}
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>

            <span className="theme-pill !bg-foreground/5 !border-foreground/10 !text-foreground/70 flex-shrink-0 !rounded-lg italic">
              Retrieval Depth
              <span className="sr-only">AVERQEL adjusts retrieval depth automatically.</span>
            </span>
            <span className="theme-pill !bg-foreground/5 !border-foreground/10 !text-foreground/70 flex-shrink-0 !rounded-lg capitalize">
              {searchMode}
            </span>
            {supportsThinking ? (
              <button
                type="button"
                onClick={() => onThinkingChange(!thinkingEnabled)}
                disabled={requestActive || queueItems.length > 0}
                className={`theme-pill flex-shrink-0 !rounded-lg transition-all disabled:opacity-60 ${
                  thinkingEnabled
                    ? "!border-primary/30 !bg-primary/10 !text-primary shadow-sm"
                    : "!bg-foreground/5 !border-foreground/10 !text-foreground/70"
                }`}
              >
                <span>Think {thinkingEnabled ? "On" : "Off"}</span>
              </button>
            ) : null}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="sr-only"
            aria-label="Choose documents to attach"
            onChange={handleFileInput}
          />
          <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
            <button
              type="button"
              aria-label="Attach documents"
              title={
                attachments.length >= MAX_QUERY_ATTACHMENTS
                  ? "Maximum 10 documents per query"
                  : "Upload to Documents Hub and wait for indexing"
              }
              onClick={() => fileInputRef.current?.click()}
              disabled={attachments.length >= MAX_QUERY_ATTACHMENTS}
              className="border-glass-border text-foreground/70 hover:text-primary flex h-9 w-9 items-center justify-center rounded-lg border transition-colors disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Paperclip size={16} />
            </button>
            <button
              type="button"
              aria-label="Choose existing Documents Hub files"
              title="Attach an existing Documents Hub file"
              aria-expanded={hubPickerOpen}
              onClick={() => setHubPickerOpen((open) => !open)}
              disabled={attachments.length >= MAX_QUERY_ATTACHMENTS}
              className="border-glass-border text-foreground/70 hover:text-primary flex h-9 w-9 items-center justify-center rounded-lg border transition-colors disabled:cursor-not-allowed disabled:opacity-45"
            >
              <FolderOpen size={16} />
            </button>
            {requestActive ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop current query"
                title="Stop current query"
                className="border-danger/30 text-danger hover:bg-danger/10 flex h-9 w-9 items-center justify-center rounded-lg border transition-colors"
              >
                <Square size={13} fill="currentColor" />
              </button>
            ) : null}
            <motion.button
              type="button"
              onClick={() => onSubmit(readyAttachments)}
              disabled={!canSubmit}
              aria-label={requestActive ? "Queue query" : "Send query"}
              title={
                queueFull
                  ? "Queue limit reached"
                  : requestActive
                    ? "Add query to queue"
                    : "Send grounded query"
              }
              className="border-primary/40 from-primary to-primary/80 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full border bg-gradient-to-br shadow-lg transition-all hover:scale-105 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:border-transparent disabled:shadow-none"
              whileHover={canSubmit ? { scale: 1.05 } : {}}
              whileTap={canSubmit ? { scale: 0.95 } : {}}
            >
              {requestActive ? <ListPlus size={17} /> : <ArrowUp size={18} strokeWidth={2.5} />}
            </motion.button>
          </div>
          <AnimatePresence>
            {hubPickerOpen ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                className="border-glass-border bg-surface-1 absolute right-2 bottom-full z-40 mb-2 w-[min(28rem,calc(100vw-2rem))] overflow-hidden rounded-xl border shadow-2xl"
                role="dialog"
                aria-label="Choose Documents Hub files"
              >
                <div className="border-glass-border flex items-center gap-2 border-b p-2.5">
                  <Search size={15} className="text-foreground/45 shrink-0" />
                  <input
                    autoFocus
                    value={hubSearch}
                    onChange={(event) => {
                      setHubSkip(0);
                      setHubDocuments([]);
                      setHubSearch(event.target.value);
                    }}
                    placeholder="Search indexed Documents Hub files"
                    aria-label="Search Documents Hub files"
                    className="text-foreground placeholder:text-foreground/40 min-w-0 flex-1 bg-transparent text-sm outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setHubPickerOpen(false)}
                    aria-label="Close file picker"
                    className="text-foreground/50 hover:text-foreground rounded p-1"
                  >
                    <X size={15} />
                  </button>
                </div>
                <div className="max-h-64 overflow-y-auto p-1.5" aria-live="polite">
                  {hubLoading && hubDocuments.length === 0 ? (
                    <div className="text-foreground/55 flex items-center gap-2 px-3 py-5 text-xs">
                      <LoaderCircle size={14} className="animate-spin" /> Searching Documents Hub…
                    </div>
                  ) : hubError ? (
                    <div className="text-danger px-3 py-4 text-xs" role="alert">
                      {hubError}
                    </div>
                  ) : hubDocuments.length === 0 ? (
                    <div className="text-foreground/55 px-3 py-5 text-xs">
                      No indexed files match this search.
                    </div>
                  ) : (
                    hubDocuments.map((document) => {
                      const alreadyAttached = attachments.some(
                        (item) => item.documentId === document.document_id,
                      );
                      return (
                        <button
                          key={document.document_id}
                          type="button"
                          disabled={alreadyAttached || attachments.length >= MAX_QUERY_ATTACHMENTS}
                          onClick={() => onExistingDocumentSelect(document)}
                          className="hover:bg-primary/10 disabled:text-foreground/35 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors disabled:cursor-not-allowed"
                        >
                          <FolderOpen size={15} className="text-primary shrink-0" />
                          <span className="min-w-0 flex-1">
                            <span className="text-foreground/85 block truncate text-xs font-medium">
                              {document.filename}
                            </span>
                            <span className="text-foreground/45 mt-0.5 block text-[10px]">
                              {(document.size_bytes / (1024 * 1024)).toFixed(2)} MiB
                              {document.tabular
                                ? " · CSV/TSV exact table index"
                                : " · Documents Hub indexed"}
                            </span>
                          </span>
                          <span className="text-primary shrink-0 text-[10px] font-semibold">
                            {alreadyAttached ? "Attached" : "Add"}
                          </span>
                        </button>
                      );
                    })
                  )}
                  {hubDocuments.length < hubTotal ? (
                    <button
                      type="button"
                      disabled={hubLoading}
                      onClick={() => setHubSkip((skip) => skip + 50)}
                      className="text-primary hover:bg-primary/10 w-full rounded-lg px-3 py-2 text-xs disabled:opacity-50"
                    >
                      {hubLoading ? "Loading…" : "Load more files"}
                    </button>
                  ) : null}
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
