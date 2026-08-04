"use client";

import {
  ArrowLeftToLine,
  Bot,
  Check,
  Copy,
  Sparkles,
  User2,
  Edit3,
  RotateCw,
  ChevronLeft,
  ChevronRight,
  X,
  AlertCircle,
  ThumbsUp,
  ThumbsDown,
  Download,
  Flag,
  FileCode,
  FileText,
  FileType,
  ShieldCheck,
  Database,
} from "lucide-react";
import { memo, useMemo, useState, useEffect, useRef } from "react";

import { fetchWithAuth } from "@/lib/api";
import { exportToDocx, exportToMarkdown, exportToPDF } from "@/lib/exportUtils";

import DeepSpaceThinkingPanel from "./DeepSpaceThinkingPanel";
import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";
import DeepSpaceMediaArtifacts from "./DeepSpaceMediaArtifacts";

import type { DeepSpaceMessage } from "../_lib/deepspace-stream";

const LARGE_THREAD_THRESHOLD = 28;
const RECENT_MESSAGE_WINDOW = 14;
const HISTORY_REVEAL_BATCH = 20;
const VIRTUAL_WINDOW_MIN_MESSAGES = 14;
const VIRTUAL_WINDOW_OVERSCAN_PX = 1200;

interface DeepSpaceThreadProps {
  messages: DeepSpaceMessage[];
  emptyPrompts: string[];
  onPromptSelect: (prompt: string) => void;
  onInsertLatestAnswer: () => void;
  onDeleteAssistant?: (messageId: string) => void;
  onRegenerate?: (messageId: string) => void;
  onStartEdit?: (messageId: string) => void;
  onCancelEdit?: (messageId: string) => void;
  onUpdateDraft?: (messageId: string, content: string) => void;
  onSaveEdit?: (messageId: string, content: string) => void;
  onActivateVersion?: (messageId: string, versionId: string) => void;
  onResolveApproval?: (approvalId: string, decision: "approved" | "denied") => Promise<void>;
  scrollMetrics?: {
    scrollTop: number;
    viewportHeight: number;
  } | null;
}

type MessageWindow = {
  startIndex: number;
  endIndex: number;
  topSpacerHeight: number;
  bottomSpacerHeight: number;
  visibleMessages: DeepSpaceMessage[];
};

type MessageLayout = {
  heights: number[];
  offsets: number[];
  totalHeight: number;
};

const MessageBubble = memo(
  function MessageBubble({
    message,
    onRegenerate,
    onStartEdit,
    onCancelEdit,
    onUpdateDraft,
    onSaveEdit,
    onActivateVersion,
    onResolveApproval,
    isLast,
  }: {
    message: DeepSpaceMessage;
    onRegenerate: (messageId: string) => void;
    onStartEdit: (messageId: string) => void;
    onCancelEdit: (messageId: string) => void;
    onUpdateDraft: (messageId: string, content: string) => void;
    onSaveEdit: (messageId: string, content: string) => void;
    onActivateVersion: (messageId: string, versionId: string) => void;
    isLast: boolean;
    onResolveApproval?: (approvalId: string, decision: "approved" | "denied") => Promise<void>;
  }) {
    const [copied, setCopied] = useState(false);
    const [feedbackState, setFeedbackState] = useState<"helpful" | "unhelpful" | null>(null);
    const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
    const [showExportMenu, setShowExportMenu] = useState(false);
    const exportMenuRef = useRef<HTMLDivElement>(null);
    const [approvalBusy, setApprovalBusy] = useState(false);
    const pendingApproval = [...(message.agentSteps ?? [])]
      .reverse()
      .find((step) => step.type === "permission_request" && step.status === "awaiting_approval");
    const pendingApprovalData = pendingApproval?.data ?? {};
    const pendingApprovalId = String(pendingApprovalData.approval_id ?? "").trim();

    useEffect(() => {
      function handleClickOutside(event: MouseEvent) {
        if (exportMenuRef.current && !exportMenuRef.current.contains(event.target as Node)) {
          setShowExportMenu(false);
        }
      }
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const submitFeedback = async (isHelpful: boolean) => {
      if (isSubmittingFeedback) return;
      setIsSubmittingFeedback(true);

      try {
        const response = await fetchWithAuth("/feedback", {
          method: "POST",
          body: JSON.stringify({ message_id: message.id, is_helpful: isHelpful }),
        });

        if (response && response.ok) {
          setFeedbackState(isHelpful ? "helpful" : "unhelpful");
        }
      } catch (error) {
        console.error("Failed to submit feedback", error);
      } finally {
        setIsSubmittingFeedback(false);
      }
    };

    const handleCopy = async () => {
      try {
        await navigator.clipboard.writeText(message.content);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      } catch {
        setCopied(false);
      }
    };

    if (message.role === "user") {
      return (
        <article
          className="mx-auto w-full max-w-[min(100%,74rem)] px-2 py-4 sm:px-3"
          style={{
            containIntrinsicSize: "120px",
            overflowAnchor: "none",
          }}
        >
          <div className="flex items-start justify-end gap-3">
            <div className="w-full max-w-[min(100%,48rem)] min-w-0 sm:max-w-[min(78%,48rem)]">
              <div className="text-muted-foreground mb-2 text-right text-[10px] font-semibold tracking-[0.24em] uppercase">
                You
              </div>
              <div
                className={`text-foreground ml-auto text-[15px] leading-7 ${
                  message.isEditing
                    ? "w-full ring-0"
                    : "border-glass-border/60 bg-surface-1/40 w-fit rounded-2xl border px-4 py-3 text-left whitespace-pre-wrap shadow-sm backdrop-blur-sm"
                }`}
              >
                {message.isEditing ? (
                  <textarea
                    value={message.draftContent ?? message.content}
                    onChange={(e) => onUpdateDraft(message.id, e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        onSaveEdit(message.id, (message.draftContent ?? message.content).trim());
                      } else if (e.key === "Escape") {
                        onCancelEdit(message.id);
                      }
                    }}
                    className="border-glass-border bg-surface-1 min-h-[100px] w-full resize-none rounded-2xl border px-4 py-3 text-[15px] outline-none"
                    autoFocus
                  />
                ) : (
                  message.content
                )}
              </div>

              <div className="text-muted-foreground mt-2 flex items-center justify-end gap-3 text-[10px]">
                {message.versionCount && message.versionCount > 1 && !message.isEditing && (
                  <div className="border-glass-border flex items-center gap-2 rounded-full border px-2 py-0.5">
                    <button
                      onClick={() => {
                        const idx = (message.activeVersionIndex ?? 1) - 1;
                        if (idx > 0) {
                          const prev = message.versions?.find((v) => v.version_index === idx);
                          if (prev) onActivateVersion(message.id, prev.id);
                        }
                      }}
                      disabled={(message.activeVersionIndex ?? 1) <= 1}
                      className="hover:text-primary disabled:opacity-30"
                    >
                      <ChevronLeft size={12} />
                    </button>
                    <span className="font-medium tracking-normal">
                      {message.activeVersionIndex} / {message.versionCount}
                    </span>
                    <button
                      onClick={() => {
                        const idx = (message.activeVersionIndex ?? 1) + 1;
                        if (idx <= (message.versionCount || 0)) {
                          const next = message.versions?.find((v) => v.version_index === idx);
                          if (next) onActivateVersion(message.id, next.id);
                        }
                      }}
                      disabled={(message.activeVersionIndex ?? 1) >= (message.versionCount || 1)}
                      className="hover:text-primary disabled:opacity-30"
                    >
                      <ChevronRight size={12} />
                    </button>
                  </div>
                )}

                {message.isEditing ? (
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() =>
                        onSaveEdit(message.id, (message.draftContent ?? message.content).trim())
                      }
                      className="text-primary hover:text-primary/80 flex items-center gap-1.5 font-bold"
                    >
                      <Check size={12} />
                      SAVE & SUBMIT
                    </button>
                    <button
                      onClick={() => onCancelEdit(message.id)}
                      className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 font-bold"
                    >
                      <X size={12} />
                      CANCEL
                    </button>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onStartEdit(message.id)}
                      className="hover:text-primary flex items-center gap-1.5 transition"
                    >
                      <Edit3 size={12} />
                      EDIT
                    </button>
                    <button
                      onClick={handleCopy}
                      aria-label={copied ? "Copied" : "Copy"}
                      className="hover:text-primary flex items-center gap-1.5 transition"
                    >
                      {copied ? <Check size={12} /> : <Copy size={12} />}
                      {copied ? "COPIED" : "COPY"}
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="theme-panel-muted mt-5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
              <User2 size={17} />
            </div>
          </div>
        </article>
      );
    }

    return (
      <article
        className="mx-auto w-full max-w-[min(100%,74rem)] px-2 py-3 sm:px-3 sm:py-4"
        style={{ containIntrinsicSize: "220px", overflowAnchor: "none" }}
      >
        <div className="relative flex items-start gap-4 p-0 transition-all duration-300">
          {/* Simple Assistant Avatar */}
          <div className="relative mt-1 shrink-0">
            <div className="text-primary/80 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5">
              <Bot size={16} />
            </div>
          </div>

          <div className="w-full min-w-0 flex-1">
            <div className="text-foreground/90 leading-relaxed">
              {message.thinkingContent?.trim() ||
              message.agentSteps?.some((step) => step.type !== "thinking") ||
              message.timeline?.length ? (
                <DeepSpaceThinkingPanel
                  content={message.thinkingContent ?? ""}
                  isStreaming={message.status === "streaming"}
                  agentSteps={message.agentSteps}
                  timeline={message.timeline}
                />
              ) : null}

              {pendingApproval && pendingApprovalId && onResolveApproval ? (
                <div className="mb-5 rounded-2xl border border-amber-400/25 bg-amber-400/[0.07] p-4 shadow-[0_12px_40px_-24px_rgba(251,191,36,0.8)]">
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-lg border border-amber-300/20 bg-amber-300/10 p-2 text-amber-200">
                      <ShieldCheck size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-amber-100">Approval required</div>
                      <p className="mt-1 text-xs leading-5 text-amber-100/70">
                        {String(
                          pendingApprovalData.message ??
                            "A connected MCP action needs your approval.",
                        )}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-semibold tracking-[0.14em] text-amber-100/60 uppercase">
                        <span>{String(pendingApprovalData.mcp_server ?? "Connected MCP")}</span>
                        <span>•</span>
                        <span>
                          {String(
                            pendingApprovalData.mcp_tool ?? pendingApproval.toolName ?? "Tool",
                          )}
                        </span>
                        <span>•</span>
                        <span>{String(pendingApprovalData.risk_level ?? "protected")}</span>
                      </div>
                      {pendingApprovalData.tool_input ? (
                        <pre className="mt-3 max-h-36 overflow-auto rounded-lg border border-white/10 bg-black/20 p-2 text-[10px] leading-5 whitespace-pre-wrap text-amber-50/65">
                          {JSON.stringify(pendingApprovalData.tool_input, null, 2)}
                        </pre>
                      ) : null}
                      <div className="mt-3 flex gap-2">
                        <button
                          type="button"
                          disabled={approvalBusy}
                          onClick={async () => {
                            setApprovalBusy(true);
                            try {
                              await onResolveApproval(pendingApprovalId, "approved");
                            } finally {
                              setApprovalBusy(false);
                            }
                          }}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-400/15 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-400/25 disabled:cursor-wait disabled:opacity-50"
                        >
                          <Check size={13} /> Approve
                        </button>
                        <button
                          type="button"
                          disabled={approvalBusy}
                          onClick={async () => {
                            setApprovalBusy(true);
                            try {
                              await onResolveApproval(pendingApprovalId, "denied");
                            } finally {
                              setApprovalBusy(false);
                            }
                          }}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs font-semibold text-white/65 transition hover:bg-white/10 disabled:cursor-wait disabled:opacity-50"
                        >
                          <X size={13} /> Deny
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              <DeepSpaceMediaArtifacts artifacts={message.artifacts} />

              <div className="prose-premium prose prose-invert max-w-none">
                {message.status === "streaming" && message.content.trim() ? (
                  <DeepSpaceMarkdownRenderer content={message.content} streaming={true} />
                ) : message.status !== "streaming" ? (
                  <DeepSpaceMarkdownRenderer content={message.content} />
                ) : null}
              </div>

              {message.memoryUsed?.length ? (
                <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-cyan-400/15 bg-cyan-400/[0.04] px-3 py-2 text-[10px] text-cyan-100/70">
                  <Database size={12} className="text-cyan-300" />
                  <span className="font-semibold">Memory used</span>
                  {message.memoryUsed.map((memory) => (
                    <span
                      key={memory.id}
                      className="rounded-full border border-cyan-300/15 bg-black/10 px-2 py-0.5"
                    >
                      {memory.key}
                    </span>
                  ))}
                </div>
              ) : null}

              {message.error ? (
                <div className="mt-6 mb-6 rounded-2xl border border-red-500/20 bg-red-500/5 p-4 text-sm shadow-lg shadow-red-500/5">
                  <div className="mb-2 flex items-center gap-2 text-red-400">
                    <AlertCircle size={14} />
                    <span className="text-[10px] font-black tracking-widest uppercase">
                      System Execution Fault
                    </span>
                  </div>
                  <p className="font-semibold text-red-200/90">{message.error.message}</p>
                  <p className="mt-1 font-mono text-[10px] text-red-400/50">{message.error.code}</p>
                </div>
              ) : null}
            </div>

            {message.status !== "streaming" ? (
              <div className="text-foreground/30 mt-5 flex flex-wrap items-center gap-4 text-[10px] font-bold">
                <div
                  className="flex items-center gap-1.5 rounded-full border border-white/5 bg-white/5 px-2 py-1 backdrop-blur-sm"
                  ref={exportMenuRef}
                >
                  {message.versionCount && message.versionCount > 1 && (
                    <div className="mr-3 flex items-center gap-3 border-r border-white/10 pr-3">
                      <button
                        onClick={() => {
                          const idx = (message.activeVersionIndex ?? 1) - 1;
                          if (idx > 0) {
                            const prev = message.versions?.find((v) => v.version_index === idx);
                            if (prev) onActivateVersion(message.id, prev.id);
                          }
                        }}
                        disabled={(message.activeVersionIndex ?? 1) <= 1}
                        className="hover:text-primary transition-colors disabled:opacity-20"
                      >
                        <ChevronLeft size={14} />
                      </button>
                      <span className="text-foreground font-mono text-[11px] tabular-nums">
                        {message.activeVersionIndex}
                        <span className="mx-1 opacity-30">/</span>
                        {message.versionCount}
                      </span>
                      <button
                        onClick={() => {
                          const idx = (message.activeVersionIndex ?? 1) + 1;
                          if (idx <= (message.versionCount || 0)) {
                            const next = message.versions?.find((v) => v.version_index === idx);
                            if (next) onActivateVersion(message.id, next.id);
                          }
                        }}
                        disabled={(message.activeVersionIndex ?? 1) >= (message.versionCount || 1)}
                        className="hover:text-primary transition-colors disabled:opacity-20"
                      >
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  )}

                  {/* 1. Helpful */}
                  <div className="group relative">
                    <button
                      type="button"
                      disabled={isSubmittingFeedback || feedbackState !== null}
                      onClick={() => submitFeedback(true)}
                      className={`flex h-7 w-7 items-center justify-center rounded-full transition-all duration-200 ${
                        feedbackState === "helpful"
                          ? "border border-emerald-500/30 bg-emerald-500/20 text-emerald-400"
                          : "text-white/40 hover:bg-white/5 hover:text-white/80"
                      }`}
                    >
                      <ThumbsUp size={12} />
                    </button>
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                      <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                        Helpful
                      </div>
                    </div>
                  </div>

                  {/* 2. Needs work */}
                  <div className="group relative">
                    <button
                      type="button"
                      disabled={isSubmittingFeedback || feedbackState !== null}
                      onClick={() => submitFeedback(false)}
                      className={`flex h-7 w-7 items-center justify-center rounded-full transition-all duration-200 ${
                        feedbackState === "unhelpful"
                          ? "border border-red-500/30 bg-red-500/20 text-red-400"
                          : "text-white/40 hover:bg-white/5 hover:text-white/80"
                      }`}
                    >
                      <ThumbsDown size={12} />
                    </button>
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                      <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                        Needs Work
                      </div>
                    </div>
                  </div>

                  {/* 3. Export */}
                  <div className="group relative">
                    <button
                      type="button"
                      onClick={() => setShowExportMenu(!showExportMenu)}
                      className={`flex h-7 w-7 items-center justify-center rounded-full text-white/40 transition-all duration-200 hover:bg-white/5 hover:text-white/80 ${
                        showExportMenu ? "bg-white/10 text-white" : ""
                      }`}
                    >
                      <Download size={12} />
                    </button>
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                      <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                        Export
                      </div>
                    </div>

                    {showExportMenu && (
                      <div className="theme-panel-strong absolute bottom-full left-0 z-[60] mb-2 w-36 overflow-hidden rounded-xl border border-white/10 bg-black/90 p-1 shadow-2xl backdrop-blur-xl">
                        <button
                          onClick={() => {
                            exportToMarkdown(message.content);
                            setShowExportMenu(false);
                          }}
                          className="text-foreground/80 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition hover:bg-white/5"
                        >
                          <FileCode size={12} className="text-cyan-400" /> Markdown
                        </button>
                        <button
                          onClick={() => {
                            exportToPDF(message.content);
                            setShowExportMenu(false);
                          }}
                          className="text-foreground/80 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition hover:bg-white/5"
                        >
                          <FileType size={12} className="text-rose-400" /> PDF
                        </button>
                        <button
                          onClick={() => {
                            exportToDocx(message.content);
                            setShowExportMenu(false);
                          }}
                          className="text-foreground/80 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition hover:bg-white/5"
                        >
                          <FileText size={12} className="text-indigo-400" /> DOCX
                        </button>
                      </div>
                    )}
                  </div>

                  {/* 4. Report */}
                  <div className="group relative">
                    <button
                      type="button"
                      onClick={() => submitFeedback(false)}
                      className="flex h-7 w-7 items-center justify-center rounded-full text-white/40 transition-all duration-200 hover:bg-red-500/10 hover:text-red-400"
                    >
                      <Flag size={12} />
                    </button>
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                      <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                        Report
                      </div>
                    </div>
                  </div>

                  <span className="mx-1 h-4 w-[1px] bg-white/10" aria-hidden="true" />

                  {/* 5. Copy */}
                  <div className="group relative">
                    <button
                      type="button"
                      onClick={handleCopy}
                      aria-label={copied ? "Copied" : "Copy"}
                      className="flex h-7 w-7 items-center justify-center rounded-full text-white/40 transition-all duration-200 hover:bg-white/5 hover:text-white/80"
                    >
                      {copied ? (
                        <Check size={12} className="text-emerald-400" />
                      ) : (
                        <Copy size={12} />
                      )}
                    </button>
                    <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                      <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                        {copied ? "Copied" : "Copy"}
                      </div>
                    </div>
                  </div>

                  {/* 6. Regenerate */}
                  {isLast && (
                    <div className="group relative">
                      <button
                        type="button"
                        onClick={() => onRegenerate(message.id)}
                        className="flex h-7 w-7 items-center justify-center rounded-full text-white/40 transition-all duration-200 hover:bg-white/5 hover:text-white/80"
                      >
                        <RotateCw size={12} />
                      </button>
                      <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                        <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                          Regenerate
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </article>
    );
  },
  (previous, next) =>
    previous.isLast === next.isLast && areMessageBubblesEqual(previous.message, next.message),
);

function areMessageBubblesEqual(previous: DeepSpaceMessage, next: DeepSpaceMessage): boolean {
  return (
    previous.id === next.id &&
    previous.role === next.role &&
    previous.content === next.content &&
    previous.rawContent === next.rawContent &&
    previous.createdAt === next.createdAt &&
    previous.status === next.status &&
    previous.thinkingContent === next.thinkingContent &&
    previous.error?.code === next.error?.code &&
    previous.error?.message === next.error?.message &&
    previous.activeVersionId === next.activeVersionId &&
    previous.activeVersionIndex === next.activeVersionIndex &&
    previous.versionCount === next.versionCount &&
    previous.versions === next.versions &&
    previous.isEditing === next.isEditing &&
    previous.draftContent === next.draftContent &&
    previous.metrics === next.metrics &&
    previous.agentSteps === next.agentSteps
  );
}

function estimateMessageHeight(message: DeepSpaceMessage): number {
  // More accurate height estimation to prevent jumping during virtualization
  const bodyLength =
    (message.content?.length ?? 0) +
    (message.thinkingContent?.length ?? 0) +
    (message.error ? 80 : 0);
  const baseHeight = message.role === "user" ? 100 : 160;
  const lineHeight = message.role === "user" ? 22 : 24;
  const estimatedLines = Math.max(1, Math.ceil(bodyLength / (message.role === "user" ? 95 : 75)));
  return baseHeight + estimatedLines * lineHeight;
}

function buildMessageLayout(messages: DeepSpaceMessage[]): MessageLayout {
  const heights = new Array<number>(messages.length);
  const offsets = new Array<number>(messages.length);
  let runningTop = 0;

  for (let index = 0; index < messages.length; index += 1) {
    const height = estimateMessageHeight(messages[index]);
    heights[index] = height;
    offsets[index] = runningTop;
    runningTop += height;
  }

  return {
    heights,
    offsets,
    totalHeight: runningTop,
  };
}

function findFirstVisibleIndex(offsets: number[], heights: number[], visibleStart: number): number {
  let low = 0;
  let high = offsets.length - 1;
  let result = offsets.length;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const messageBottom = offsets[mid] + heights[mid];
    if (messageBottom >= visibleStart) {
      result = mid;
      high = mid - 1;
    } else {
      low = mid + 1;
    }
  }

  return result;
}

function findFirstInvisibleIndex(
  offsets: number[],
  visibleEnd: number,
  startIndex: number,
): number {
  let low = startIndex;
  let high = offsets.length - 1;
  let result = offsets.length;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (offsets[mid] < visibleEnd) {
      low = mid + 1;
    } else {
      result = mid;
      high = mid - 1;
    }
  }

  return result;
}

function buildWindowedMessages(
  messages: DeepSpaceMessage[],
  scrollMetrics: { scrollTop: number; viewportHeight: number } | null | undefined,
): MessageWindow {
  if (messages.length === 0) {
    return {
      startIndex: 0,
      endIndex: 0,
      topSpacerHeight: 0,
      bottomSpacerHeight: 0,
      visibleMessages: [],
    };
  }

  if (!scrollMetrics || messages.length <= VIRTUAL_WINDOW_MIN_MESSAGES) {
    return {
      startIndex: 0,
      endIndex: messages.length,
      topSpacerHeight: 0,
      bottomSpacerHeight: 0,
      visibleMessages: messages,
    };
  }

  const { heights, offsets, totalHeight } = buildMessageLayout(messages);
  const overscan = Math.max(
    VIRTUAL_WINDOW_OVERSCAN_PX,
    Math.round(scrollMetrics.viewportHeight * 1.5),
  );
  const visibleStart = Math.max(0, scrollMetrics.scrollTop - overscan);
  const visibleEnd = Math.min(
    totalHeight,
    scrollMetrics.scrollTop + scrollMetrics.viewportHeight + overscan,
  );

  const startIndex = findFirstVisibleIndex(offsets, heights, visibleStart);
  const endIndex = findFirstInvisibleIndex(offsets, visibleEnd, startIndex);

  if (startIndex >= messages.length) {
    const lastIndex = messages.length - 1;
    return {
      startIndex: lastIndex,
      endIndex: messages.length,
      topSpacerHeight: offsets[lastIndex] ?? 0,
      bottomSpacerHeight: 0,
      visibleMessages: messages.slice(lastIndex),
    };
  }

  if (startIndex === endIndex) {
    const fallbackEnd = Math.min(messages.length, startIndex + 1);
    const lastVisibleIndex = Math.max(0, fallbackEnd - 1);
    return {
      startIndex,
      endIndex: fallbackEnd,
      topSpacerHeight: offsets[startIndex] ?? 0,
      bottomSpacerHeight: Math.max(
        0,
        totalHeight - (offsets[lastVisibleIndex] ?? 0) - (heights[lastVisibleIndex] ?? 0),
      ),
      visibleMessages: messages.slice(startIndex, fallbackEnd),
    };
  }

  const lastVisibleIndex = Math.min(messages.length - 1, endIndex - 1);
  return {
    startIndex,
    endIndex,
    topSpacerHeight: offsets[startIndex] ?? 0,
    bottomSpacerHeight: Math.max(
      0,
      totalHeight - (offsets[lastVisibleIndex] ?? 0) - (heights[lastVisibleIndex] ?? 0),
    ),
    visibleMessages: messages.slice(startIndex, endIndex),
  };
}

export default function DeepSpaceThread({
  messages,
  emptyPrompts,
  onPromptSelect,
  onRegenerate = () => {},
  onStartEdit = () => {},
  onCancelEdit = () => {},
  onUpdateDraft = () => {},
  onSaveEdit = () => {},
  onActivateVersion = () => {},
  onResolveApproval,
  scrollMetrics = null,
}: DeepSpaceThreadProps) {
  const [revealedHistoryCount, setRevealedHistoryCount] = useState(RECENT_MESSAGE_WINDOW);

  const compactedHistoryMessages = useMemo(() => {
    if (messages.length <= LARGE_THREAD_THRESHOLD) {
      return messages;
    }
    return messages.slice(-Math.max(revealedHistoryCount, RECENT_MESSAGE_WINDOW));
  }, [messages, revealedHistoryCount]);

  const renderSourceMessages = scrollMetrics ? messages : compactedHistoryMessages;

  const isCompactedHistory =
    !scrollMetrics &&
    messages.length > LARGE_THREAD_THRESHOLD &&
    compactedHistoryMessages.length < messages.length;
  const windowedMessages = useMemo(
    () => buildWindowedMessages(renderSourceMessages, scrollMetrics),
    [renderSourceMessages, scrollMetrics],
  );
  const shouldVirtualize = windowedMessages.visibleMessages.length < renderSourceMessages.length;

  if (messages.length === 0) {
    return (
      <div className="flex h-full min-h-0 flex-col px-2 py-4">
        <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <div className="theme-accent-pill mb-4 inline-flex rounded-xl p-3 shadow-[0_20px_56px_-36px_rgba(var(--primary),0.28)]">
                <Sparkles size={24} />
              </div>
              <h1 className="text-foreground text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">
                DeepSpace chat
              </h1>
              <p className="text-foreground/60 mt-3 max-w-2xl text-sm leading-7 sm:text-[15px]">
                Open conversation for drafting, ideation, rewriting, and general help.
              </p>
            </div>
            <button
              type="button"
              aria-label="Insert latest answer"
              title="Insert latest answer"
              disabled
              className="theme-panel-muted text-muted-foreground border-glass-border bg-surface-2/40 flex h-11 w-11 items-center justify-center rounded-full border opacity-35"
            >
              <ArrowLeftToLine size={17} />
            </button>
          </div>

          <div className="grid w-full grid-cols-1 gap-3 md:grid-cols-2">
            {emptyPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => onPromptSelect(prompt)}
                className="theme-panel-muted text-foreground/80 hover:border-primary/25 min-h-[7.5rem] rounded-xl p-5 text-left text-[15px] leading-8 transition"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      data-deepspace-thread-root="true"
      className="space-y-1 pt-5 pb-10 sm:pt-6"
      style={{ overflowAnchor: "none" }}
    >
      {isCompactedHistory ? (
        <div className="mx-auto w-full max-w-[min(100%,74rem)] px-2 pt-2 sm:px-3">
          <div className="border-glass-border bg-surface-2/70 flex items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-[11px] font-medium text-white/70">
            <span>
              Showing the most recent {compactedHistoryMessages.length} of {messages.length}{" "}
              messages to keep large missions fast.
            </span>
            <button
              type="button"
              onClick={() =>
                setRevealedHistoryCount((current) =>
                  Math.min(messages.length, current + HISTORY_REVEAL_BATCH),
                )
              }
              className="text-primary hover:text-primary/80 font-semibold"
            >
              Load older messages
            </button>
          </div>
        </div>
      ) : null}

      {windowedMessages.topSpacerHeight > 0 ? (
        <div aria-hidden="true" style={{ height: `${windowedMessages.topSpacerHeight}px` }} />
      ) : null}

      {windowedMessages.visibleMessages.map((message, index) => {
        const renderIndex = windowedMessages.startIndex + index;
        const bubble = (
          <MessageBubble
            message={message}
            isLast={renderIndex === renderSourceMessages.length - 1}
            onRegenerate={onRegenerate}
            onStartEdit={onStartEdit}
            onCancelEdit={onCancelEdit}
            onUpdateDraft={onUpdateDraft}
            onSaveEdit={onSaveEdit}
            onActivateVersion={onActivateVersion}
            onResolveApproval={onResolveApproval}
          />
        );

        return (
          <div key={message.id} data-message-id={message.id} data-role={message.role}>
            <div>{bubble}</div>
          </div>
        );
      })}

      {shouldVirtualize && windowedMessages.bottomSpacerHeight > 0 ? (
        <div aria-hidden="true" style={{ height: `${windowedMessages.bottomSpacerHeight}px` }} />
      ) : null}
    </div>
  );
}
