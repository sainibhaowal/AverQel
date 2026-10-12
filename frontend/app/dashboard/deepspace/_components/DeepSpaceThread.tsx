"use client";

import {
  ArrowLeftToLine,
  Bot,
  Check,
  Copy,
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
  ArrowUp,
  LoaderCircle,
  MessageCircleQuestion,
  Activity,
  Timer,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useCallback, useId, useMemo, useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";

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
const EMPTY_RETRYABLE_REQUEST_IDS: ReadonlySet<string> = new Set();
const ROTATING_PROMPT_BANK = [
  "Turn a rough idea into a clear, practical plan.",
  "Rewrite this message so it sounds concise and confident.",
  "Compare these options and explain the trade-offs.",
  "Help me break this complex task into the next three steps.",
  "Summarize the important points and highlight what is missing.",
  "Review this draft and suggest a stronger structure.",
  "Explain this topic simply, then give me an expert version.",
  "Find the risks in this approach and propose safer alternatives.",
  "Create a focused checklist I can use to finish this work.",
  "Transform these notes into a polished update for my team.",
  "Help me decide what deserves attention first.",
  "Ask the right questions before helping me solve this problem.",
] as const;
const ROTATING_WELCOME_STATUSES = [
  "READY TO WORK",
  "READY TO STREAM IDEAS",
  "READY TO FIND CLARITY",
  "READY TO SEARCH",
  "READY TO OBSERVE DETAILS",
  "READY TO EXPLORE",
] as const;
const PROMPT_MOTION_EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];
const PROMPT_MOTION_VARIANTS = [
  {
    cardInitial: { opacity: 0, y: 12, scale: 0.985 },
    cardExit: { opacity: 0, y: -8, scale: 0.99 },
    textInitial: { opacity: 0, y: 5 },
    textExit: { opacity: 0, y: -3 },
  },
  {
    cardInitial: { opacity: 0, x: 11, scale: 0.99 },
    cardExit: { opacity: 0, x: -8, scale: 0.99 },
    textInitial: { opacity: 0, x: 6 },
    textExit: { opacity: 0, x: -4 },
  },
  {
    cardInitial: { opacity: 0, y: -10, scale: 0.99 },
    cardExit: { opacity: 0, y: 7, scale: 0.99 },
    textInitial: { opacity: 0, y: -4 },
    textExit: { opacity: 0, y: 3 },
  },
  {
    cardInitial: { opacity: 0, x: -10, y: 3, scale: 0.99 },
    cardExit: { opacity: 0, x: 8, y: -2, scale: 0.99 },
    textInitial: { opacity: 0, scale: 0.985 },
    textExit: { opacity: 0, scale: 0.99 },
  },
] as const;

function getPromptMotionVariant(prompt: string, index: number, rotation: number) {
  let hash = Math.imul(rotation + 1, 0x45d9f3b) ^ Math.imul(index + 1, 0x27d4eb2d);
  for (let offset = 0; offset < prompt.length; offset += 1) {
    hash = Math.imul(hash ^ prompt.charCodeAt(offset), 16777619);
  }
  return PROMPT_MOTION_VARIANTS[(hash >>> 0) % PROMPT_MOTION_VARIANTS.length];
}

function getExecutionErrorHeading(error: NonNullable<DeepSpaceMessage["error"]>): string {
  if (error.category === "request" || error.code === "LLM_REQUEST_REJECTED") {
    return "Request rejected";
  }
  if (error.code === "LLM_RATE_LIMITED") return "Provider rate limit";
  if (error.code === "LLM_PROVIDER_AUTH_REJECTED") return "Provider credentials rejected";
  if (error.code === "LLM_PROVIDER_ACCESS_DENIED") return "Provider access denied";
  if (error.code === "LLM_MODEL_OR_ENDPOINT_NOT_FOUND") return "Model or endpoint not found";
  if (error.code === "LLM_PROVIDER_UNAVAILABLE") return "Provider unavailable";
  if (error.category === "provider" || error.code === "LLM_REQUEST_FAILED") {
    return "Provider error";
  }
  return "System execution error";
}

function formatUserName(value?: string | null): string {
  const source = (value || "")
    .split("@")[0]
    .replace(/[._-]+/g, " ")
    .trim();
  if (!source) return "there";
  return source
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

interface DeepSpaceThreadProps {
  messages: DeepSpaceMessage[];
  emptyPrompts: string[];
  userName?: string | null;
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
  onSubmitUserQuestion?: (answer: string) => Promise<void>;
  onRetryFailedTurn?: (requestId: string) => void;
  retryableRequestIds?: ReadonlySet<string>;
  retryingRequestId?: string | null;
  retryActionDisabled?: boolean;
  queuedAssistantId?: string | null;
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

function QuestionCard({
  question,
  options,
  onSubmit,
}: {
  question: string;
  options: string[];
  onSubmit: (answer: string) => Promise<void>;
}) {
  const [customAnswer, setCustomAnswer] = useState("");
  const [otherOpen, setOtherOpen] = useState(options.length === 0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const customAnswerId = useId();

  const submit = async (answer: string) => {
    const normalized = answer.trim();
    if (!normalized || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmit(normalized);
    } catch {
      setSubmitError("The answer could not be sent. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 14, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.24, ease: "easeOut" }}
      aria-label="DeepSpace question"
      className="deepspace-question-card relative mt-5 w-full max-w-4xl overflow-hidden rounded-2xl border border-white/10 bg-[linear-gradient(145deg,rgba(16,25,27,.96),rgba(12,19,21,.98))] p-5 shadow-[0_8px_24px_-18px_rgba(0,0,0,.75)] sm:p-6"
    >
      <div className="relative flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-cyan-200/15 bg-cyan-300/[0.07] text-cyan-100/85">
          <MessageCircleQuestion size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="deepspace-question-title text-[10px] font-semibold tracking-[0.12em] text-cyan-100/70 uppercase">
              Your input is needed
            </span>
            <span className="deepspace-question-status rounded-full border border-cyan-200/15 bg-cyan-200/[0.06] px-2 py-0.5 text-[10px] font-medium text-cyan-100/65">
              Waiting for you
            </span>
          </div>
          <p className="deepspace-question-prompt mt-2.5 text-[15px] leading-6 font-medium text-white/95">
            {question}
          </p>
          <p className="deepspace-question-hint mt-1.5 text-xs leading-5 text-white/55">
            Choose an answer to send it and continue the task.
          </p>
        </div>
      </div>

      {options.length > 0 ? (
        <div className="deepspace-question-options relative mt-4 overflow-hidden rounded-xl border border-white/10 bg-white/[0.025]">
          {options.map((option, index) => (
            <motion.button
              key={option + "-" + index}
              type="button"
              disabled={submitting}
              onClick={() => void submit(option)}
              whileTap={{ scale: 0.995 }}
              aria-label={index === 0 ? "Recommended: " + option : "Choose: " + option}
              className="deepspace-question-option group flex min-h-[60px] w-full items-center justify-between gap-3 border-b border-white/10 bg-transparent px-4 py-3 text-left text-sm text-white/80 transition-colors hover:bg-white/[0.055] hover:text-white focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-cyan-200/60 focus-visible:outline-none focus-visible:ring-inset disabled:cursor-wait disabled:opacity-50"
            >
              <span className="min-w-0 flex-1">
                {index === 0 ? (
                  <span className="deepspace-question-recommended mb-1 inline-flex rounded-md bg-cyan-200/[0.08] px-1.5 py-0.5 text-[9px] font-semibold tracking-[0.08em] text-cyan-100/75 uppercase">
                    Recommended
                  </span>
                ) : null}
                <span className="deepspace-question-option-text block leading-5 break-words">
                  {option}
                </span>
              </span>
              <ChevronRight
                size={16}
                className="deepspace-question-option-arrow shrink-0 text-cyan-100/45 transition-transform group-hover:translate-x-0.5"
              />
            </motion.button>
          ))}
          <button
            type="button"
            disabled={submitting}
            onClick={() => setOtherOpen((open) => !open)}
            aria-expanded={otherOpen}
            aria-controls={customAnswerId}
            aria-label={otherOpen ? "Hide custom answer" : "Write a different answer"}
            className="deepspace-question-other deepspace-question-option group flex min-h-[60px] w-full items-center gap-3 border-b-0 bg-transparent px-4 py-3 text-left transition-colors hover:bg-white/[0.055] disabled:opacity-50"
          >
            <Edit3 size={16} className="deepspace-question-other-icon shrink-0 text-cyan-100/65" />
            <span className="min-w-0 flex-1">
              <span className="deepspace-question-other-label block text-xs font-medium text-white/75">
                {otherOpen ? "Hide custom answer" : "Write a different answer"}
              </span>
              <span className="deepspace-question-other-copy mt-0.5 block text-[11px] text-white/45">
                Use your own words instead of a suggestion
              </span>
            </span>
            <ChevronRight
              size={15}
              className={`deepspace-question-other-chevron shrink-0 text-white/40 transition-transform ${otherOpen ? "rotate-90" : ""}`}
            />
          </button>
        </div>
      ) : null}

      <div className={options.length > 0 ? "relative" : "relative mt-3"}>
        {options.length === 0 ? (
          <p className="deepspace-question-custom-label mb-2 text-xs font-medium text-white/70">
            Your answer
          </p>
        ) : null}
        <AnimatePresence initial={false}>
          {otherOpen ? (
            <motion.form
              initial={{ opacity: 0, height: 0, y: -5 }}
              animate={{ opacity: 1, height: "auto", y: 0 }}
              exit={{ opacity: 0, height: 0, y: -5 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              id={customAnswerId}
              onSubmit={(event) => {
                event.preventDefault();
                void submit(customAnswer);
              }}
              className="mt-2.5 flex items-end gap-2 overflow-hidden"
            >
              <textarea
                value={customAnswer}
                onChange={(event) => setCustomAnswer(event.target.value.slice(0, 4000))}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit(customAnswer);
                  }
                }}
                autoFocus={options.length === 0 || otherOpen}
                aria-label="Write your answer"
                rows={3}
                disabled={submitting}
                placeholder="Write your answer…"
                className="deepspace-question-input min-h-[76px] min-w-0 flex-1 resize-y rounded-xl border border-white/10 bg-black/20 px-3 py-2.5 text-sm leading-5 text-white/85 transition-colors outline-none placeholder:text-white/35 focus:border-cyan-200/40 focus:bg-black/25 focus-visible:ring-2 focus-visible:ring-cyan-200/20"
              />
              <button
                type="submit"
                disabled={!customAnswer.trim() || submitting}
                aria-label="Send answer"
                title="Send answer and continue the task"
                className="deepspace-question-submit flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-cyan-200/20 bg-cyan-300/10 text-cyan-100/85 transition-colors hover:bg-cyan-300/20 focus-visible:ring-2 focus-visible:ring-cyan-200/60 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-35"
              >
                {submitting ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : (
                  <ArrowUp size={16} />
                )}
              </button>
            </motion.form>
          ) : null}
        </AnimatePresence>
      </div>
      {submitting ? (
        <div
          role="status"
          className="deepspace-question-sending mt-3 flex items-center gap-2 text-xs font-medium text-cyan-100/65"
        >
          <LoaderCircle size={12} className="animate-spin" /> Sending answer and resuming the task…
        </div>
      ) : null}
      {submitError ? (
        <p role="alert" className="mt-3 text-xs text-rose-200/85">
          {submitError}
        </p>
      ) : null}
    </motion.section>
  );
}

function ResponseLoadingDots() {
  return (
    <div
      className="deepspace-response-dots"
      role="status"
      aria-label="AverQel is preparing a response"
    >
      <span className="deepspace-response-dot" aria-hidden="true" />
      <span className="deepspace-response-dot" aria-hidden="true" />
      <span className="deepspace-response-dot" aria-hidden="true" />
      <span className="sr-only">Preparing response…</span>
    </div>
  );
}

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
    onSubmitUserQuestion,
    onRetryFailedTurn,
    canRetryFailedPrompt,
    isRetryingFailedPrompt,
    isRetryActionDisabled,
    isQueued,
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
    isQueued: boolean;
    onResolveApproval?: (approvalId: string, decision: "approved" | "denied") => Promise<void>;
    onSubmitUserQuestion?: (answer: string) => Promise<void>;
    onRetryFailedTurn?: (requestId: string) => void;
    canRetryFailedPrompt: boolean;
    isRetryingFailedPrompt: boolean;
    isRetryActionDisabled: boolean;
  }) {
    const [copied, setCopied] = useState(false);
    const prefersReducedMotion = useReducedMotion();
    const [feedbackState, setFeedbackState] = useState<"helpful" | "unhelpful" | null>(null);
    const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
    const [showExportMenu, setShowExportMenu] = useState(false);
    const [exportMenuPosition, setExportMenuPosition] = useState<{
      top: number;
      left: number;
    } | null>(null);
    const exportMenuId = useId();
    const exportMenuRef = useRef<HTMLDivElement>(null);
    const exportButtonRef = useRef<HTMLButtonElement>(null);
    const exportMenuOverlayRef = useRef<HTMLDivElement>(null);
    const closeExportMenu = useCallback(() => {
      setShowExportMenu(false);
      setExportMenuPosition(null);
    }, []);
    const [approvalBusy, setApprovalBusy] = useState(false);
    const pendingApprovalStep = [...(message.agentSteps ?? [])]
      .reverse()
      .find((step) => step.type === "permission_request" && step.status === "awaiting_approval");
    // History and live replay can contain the approval in either the durable
    // agent-step list or the reconstructed timeline. Use both sources so a
    // permission card cannot disappear when only timeline events were saved.
    const pendingApprovalTimeline = [...(message.timeline ?? [])]
      .reverse()
      .find((step) => step.type === "permission" && step.status === "awaiting_approval");
    const pendingApprovalData =
      pendingApprovalStep?.data ?? pendingApprovalTimeline?.data ?? ({} as Record<string, unknown>);
    const pendingApproval = pendingApprovalStep ?? pendingApprovalTimeline;
    const pendingApprovalId = String(pendingApprovalData.approval_id ?? "").trim();
    const pendingQuestion = [...(message.agentSteps ?? [])]
      .reverse()
      .find(
        (step) =>
          !message.userQuestionAnswer?.trim() &&
          step.type === "ask_user_question" &&
          step.status === "awaiting_approval" &&
          typeof step.data?.question_id === "string" &&
          !step.data.answer_submitted,
      );
    const pendingQuestionData = pendingQuestion?.data ?? {};
    const pendingQuestionText = String(
      pendingQuestionData.message ??
        pendingQuestionData.question ??
        pendingQuestionData.details ??
        "DeepSpace needs your input before continuing.",
    ).trim();
    const pendingQuestionOptions = Array.isArray(pendingQuestionData.options)
      ? pendingQuestionData.options
          .map((option) => String(option ?? "").trim())
          .filter(Boolean)
          .slice(0, 8)
      : [];
    const responseMetrics = message.metrics;
    const showResponsePerformance = Boolean(
      responseMetrics &&
      (responseMetrics.tokensPerSecond !== undefined ||
        responseMetrics.timeToFirstTokenMs !== undefined ||
        responseMetrics.providerTimeToFirstOutputMs !== undefined),
    );
    const speedValue = responseMetrics?.tokensPerSecond;
    const speedLabel =
      typeof speedValue === "number" && Number.isFinite(speedValue) && speedValue >= 0
        ? `${speedValue > 0 && speedValue < 0.05 ? "<0.1" : speedValue.toFixed(1)} tok/s`
        : "Tok/s —";
    const speedDescription =
      typeof speedValue === "number" && Number.isFinite(speedValue)
        ? "Exact provider-reported output tokens divided by the server-observed interval between the first and last provider output events across generation rounds. Provider counts may include hidden reasoning or tool-call tokens; no reasoning text is shown."
        : responseMetrics?.tokensPerSecondUnavailableReason === "buffered_provider_fallback"
          ? "Speed is unavailable because this provider used a buffered one-shot fallback instead of a live stream."
          : responseMetrics?.tokensPerSecondUnavailableReason ===
              "usage_missing_for_generation_round"
            ? "Speed is unavailable because at least one generation round did not report exact output-token usage."
            : responseMetrics?.tokensPerSecondUnavailableReason === "insufficient_stream_samples"
              ? "Speed is unavailable because the provider did not deliver enough separate output events to measure a stream interval."
              : responseMetrics?.tokensPerSecondUnavailableReason === "stream_interval_too_short"
                ? "Speed is unavailable because the measured output interval was too short for a stable rate."
                : "Speed is unavailable because this provider did not report exact output-token usage.";
    const ttftValue = responseMetrics?.timeToFirstTokenMs;
    const ttftLabel =
      typeof ttftValue === "number" && Number.isFinite(ttftValue) && ttftValue >= 0
        ? ttftValue >= 1000
          ? `${(ttftValue / 1000).toFixed(2)}s`
          : `${Math.round(ttftValue)}ms`
        : "—";
    const providerFirstOutputValue = responseMetrics?.providerTimeToFirstOutputMs;
    const providerFirstOutputLabel =
      typeof providerFirstOutputValue === "number" &&
      Number.isFinite(providerFirstOutputValue) &&
      providerFirstOutputValue >= 0
        ? providerFirstOutputValue >= 1000
          ? `${(providerFirstOutputValue / 1000).toFixed(2)}s`
          : `${Math.round(providerFirstOutputValue)}ms`
        : "—";

    useEffect(() => {
      function handleClickOutside(event: MouseEvent) {
        const target = event.target as Node;
        if (
          exportMenuRef.current?.contains(target) ||
          exportMenuOverlayRef.current?.contains(target)
        ) {
          return;
        }
        closeExportMenu();
      }
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [closeExportMenu]);

    useEffect(() => {
      if (!showExportMenu) {
        return;
      }

      const updateExportMenuPosition = () => {
        const trigger = exportButtonRef.current;
        if (!trigger) return;

        const triggerRect = trigger.getBoundingClientRect();
        const menuRect = exportMenuOverlayRef.current?.getBoundingClientRect();
        const menuWidth = menuRect?.width || 144;
        const menuHeight = menuRect?.height || 104;
        const viewportPadding = 8;
        const gap = 8;
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const aboveTop = triggerRect.top - menuHeight - gap;
        const belowTop = triggerRect.bottom + gap;
        const hasRoomAbove = aboveTop >= viewportPadding;
        const hasRoomBelow = belowTop + menuHeight <= viewportHeight - viewportPadding;
        const top = hasRoomAbove
          ? aboveTop
          : hasRoomBelow
            ? belowTop
            : Math.max(
                viewportPadding,
                Math.min(aboveTop, viewportHeight - menuHeight - viewportPadding),
              );
        const maxLeft = Math.max(viewportPadding, viewportWidth - menuWidth - viewportPadding);
        const left = Math.max(
          viewportPadding,
          Math.min(triggerRect.left + (triggerRect.width - menuWidth) / 2, maxLeft),
        );

        setExportMenuPosition({ top, left });
      };

      const positionFrame = window.requestAnimationFrame(updateExportMenuPosition);
      window.addEventListener("resize", updateExportMenuPosition);
      window.addEventListener("scroll", updateExportMenuPosition, true);

      const handleEscape = (event: KeyboardEvent) => {
        if (event.key === "Escape") closeExportMenu();
      };
      document.addEventListener("keydown", handleEscape);

      return () => {
        window.cancelAnimationFrame(positionFrame);
        window.removeEventListener("resize", updateExportMenuPosition);
        window.removeEventListener("scroll", updateExportMenuPosition, true);
        document.removeEventListener("keydown", handleEscape);
      };
    }, [showExportMenu, closeExportMenu]);

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
          className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 mx-auto w-full max-w-[min(100%,74rem)] px-2 py-4 motion-safe:duration-300 motion-safe:ease-out sm:px-3"
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
                {message.attachments?.length ? (
                  <div
                    className="mt-3 grid gap-2 sm:grid-cols-2"
                    aria-label="Attachments sent with this message"
                  >
                    {message.attachments.map((attachment) => (
                      <button
                        key={attachment.id}
                        type="button"
                        onClick={() =>
                          window.dispatchEvent(
                            new CustomEvent("deepspace-library-open", {
                              detail: { fileId: attachment.id },
                            }),
                          )
                        }
                        className="flex min-w-0 items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-50/70 px-2 py-2 text-left text-xs hover:bg-emerald-100 dark:bg-emerald-950/30"
                        title="Open this secure file in Library"
                      >
                        <FileText size={15} className="shrink-0 text-emerald-600" />
                        <span className="min-w-0">
                          <span className="block truncate font-semibold">{attachment.name}</span>
                          <span className="text-[10px] text-emerald-800/70">Saved in Library</span>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="text-muted-foreground mt-2 flex items-center justify-end gap-3 text-[10px]">
                {message.versionCount && message.versionCount > 1 && !message.isEditing && (
                  <div className="border-glass-border flex items-center gap-2 rounded-full border px-2 py-0.5">
                    <button
                      type="button"
                      aria-label="Show previous prompt version"
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
                    <span aria-live="polite" className="font-medium tracking-normal">
                      {message.activeVersionIndex} / {message.versionCount}
                    </span>
                    <button
                      type="button"
                      aria-label="Show next prompt version"
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

    // The response dots are only a first-frame placeholder. Thinking text,
    // timeline entries, tool activity, or the answer itself all mean the
    // stream has started, so the placeholder must disappear immediately.
    const hasAssistantProgress = Boolean(
      message.content.trim() ||
      message.thinkingContent?.trim() ||
      message.agentSteps?.length ||
      message.timeline?.length,
    );
    const showResponseDots = message.status === "streaming" && !hasAssistantProgress;

    return (
      <article
        className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 mx-auto w-full max-w-[min(100%,74rem)] px-2 py-3 motion-safe:duration-300 motion-safe:ease-out sm:px-3 sm:py-4"
        style={{ containIntrinsicSize: "220px", overflowAnchor: "none" }}
      >
        <div className="relative flex items-start gap-4 p-0">
          {/* Simple Assistant Avatar */}
          <div className="mt-1 grid h-8 w-14 shrink-0 grid-cols-[2rem_1.5rem] items-start">
            <div className="text-primary/80 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5">
              <Bot size={16} />
            </div>
            {showResponseDots ? (
              <div className="flex h-8 items-center justify-start">
                <ResponseLoadingDots />
              </div>
            ) : null}
          </div>

          <div className="w-full min-w-0 flex-1">
            <div className="text-foreground/90 leading-relaxed">
              {message.thinkingContent?.trim() ||
              message.agentSteps?.some((step) => step.type !== "thinking") ||
              message.timeline?.length ||
              message.status === "streaming" ? (
                <DeepSpaceThinkingPanel
                  content={message.thinkingContent ?? ""}
                  isStreaming={message.status === "streaming"}
                  isQueued={isQueued}
                  agentSteps={message.agentSteps}
                  timeline={message.timeline}
                  startedAt={message.createdAt}
                />
              ) : null}

              {pendingApproval && pendingApprovalId && onResolveApproval ? (
                <div className="motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 mb-5 rounded-2xl border border-amber-400/25 bg-amber-400/[0.07] p-4 shadow-[0_12px_40px_-24px_rgba(251,191,36,0.8)] motion-safe:duration-300 motion-safe:ease-out">
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
                            pendingApprovalData.mcp_tool ?? pendingApproval?.toolName ?? "Tool",
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

              {pendingQuestion && onSubmitUserQuestion ? (
                <QuestionCard
                  question={pendingQuestionText}
                  options={pendingQuestionOptions}
                  onSubmit={onSubmitUserQuestion}
                />
              ) : null}

              {message.userQuestionAnswer ? (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="deepspace-answer-strip mb-4 flex items-center gap-2 rounded-xl border border-cyan-300/15 bg-cyan-300/[0.05] px-3 py-2 text-xs text-cyan-100/80"
                >
                  <MessageCircleQuestion
                    size={14}
                    className="deepspace-answer-icon shrink-0 text-cyan-300"
                  />
                  <span className="deepspace-answer-label font-semibold text-cyan-200/80">
                    Your answer
                  </span>
                  <span className="deepspace-answer-text min-w-0 truncate">
                    {message.userQuestionAnswer}
                  </span>
                </motion.div>
              ) : null}

              <DeepSpaceMediaArtifacts
                artifacts={message.artifacts}
                status={message.mediaStatus}
                onRegenerate={() => onRegenerate(message.id)}
              />

              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={message.activeVersionId ?? message.id}
                  initial={{ opacity: 0, y: 2 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -2 }}
                  transition={{ duration: prefersReducedMotion ? 0 : 0.16, ease: "easeOut" }}
                  aria-live="polite"
                  aria-atomic="true"
                  className="prose-premium prose prose-invert max-w-none"
                >
                  {pendingQuestion ? null : message.status === "streaming" &&
                    message.content.trim() ? (
                    <DeepSpaceMarkdownRenderer content={message.content} streaming={true} />
                  ) : message.status !== "streaming" ? (
                    <DeepSpaceMarkdownRenderer content={message.content} />
                  ) : null}
                </motion.div>
              </AnimatePresence>

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
                <div className="deepspace-execution-error mt-6 mb-6 rounded-2xl border border-red-500/20 bg-red-500/5 p-4 text-sm shadow-lg shadow-red-500/5">
                  <div className="deepspace-execution-error-title mb-2 flex flex-wrap items-center justify-between gap-2 text-red-400">
                    <span className="flex min-w-0 items-center gap-2">
                      <AlertCircle size={14} />
                      <span className="text-[10px] font-black tracking-widest uppercase">
                        {getExecutionErrorHeading(message.error)}
                      </span>
                    </span>
                    {canRetryFailedPrompt && message.clientRequestId && onRetryFailedTurn ? (
                      <button
                        type="button"
                        disabled={isRetryingFailedPrompt || isRetryActionDisabled}
                        onClick={() => {
                          const requestId = message.clientRequestId;
                          if (requestId) onRetryFailedTurn(requestId);
                        }}
                        aria-label={
                          isRetryingFailedPrompt ? "Retrying failed prompt" : "Retry failed prompt"
                        }
                        title="Retry the saved prompt with its original attachments. If its checkpoint expired, completed actions may run again."
                        className="deepspace-execution-error-retry inline-flex shrink-0 items-center gap-1.5 rounded-full border border-red-300/20 bg-red-300/[0.08] px-2.5 py-1 text-[10px] font-semibold text-red-100/80 transition-colors hover:border-red-300/35 hover:bg-red-300/[0.14] hover:text-red-50 focus-visible:ring-2 focus-visible:ring-red-300/50 focus-visible:outline-none disabled:cursor-wait disabled:opacity-60"
                      >
                        {isRetryingFailedPrompt ? (
                          <LoaderCircle size={12} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <RotateCw size={12} aria-hidden="true" />
                        )}
                        {isRetryingFailedPrompt ? "Retrying…" : "Retry"}
                      </button>
                    ) : null}
                  </div>
                  <p className="deepspace-execution-error-message font-semibold text-red-200/90">
                    {message.error.message}
                  </p>
                  <p className="deepspace-execution-error-code mt-1 font-mono text-[10px] text-red-400/50">
                    {message.error.code}
                  </p>
                </div>
              ) : null}
            </div>

            {message.status !== "streaming" ? (
              <div className="text-foreground/30 mt-5 flex flex-wrap items-center justify-between gap-3 text-[10px] font-bold">
                {showResponsePerformance ? (
                  <div
                    role="group"
                    aria-label="Response performance"
                    className="flex flex-wrap items-center gap-2"
                  >
                    <span
                      tabIndex={0}
                      title={speedDescription}
                      aria-label={`${speedLabel}. ${speedDescription}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-white/5 px-2 py-1 font-medium text-white/55 outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/50"
                    >
                      <Activity size={11} aria-hidden="true" />
                      {speedLabel}
                    </span>
                    <span
                      tabIndex={0}
                      title="End-to-end time from the server beginning to handle this DeepSpace request to the first visible answer text. This includes routing, context preparation, provider waiting, and any reasoning or tool work before the answer."
                      aria-label={`Time to first token: ${ttftLabel}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-white/5 px-2 py-1 font-medium text-white/55 outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/50"
                    >
                      <Timer size={11} aria-hidden="true" />
                      TTFT {ttftLabel}
                    </span>
                    {responseMetrics?.providerTimeToFirstOutputMs !== undefined ? (
                      <span
                        tabIndex={0}
                        title="Time from the first provider or connector request to its first output event, which may be reasoning, a tool call, or answer text. It is a connector-level measurement, not the provider's internal model-compute time; Codex timing includes the desktop relay."
                        aria-label={`Provider first output: ${providerFirstOutputLabel}`}
                        className="inline-flex items-center gap-1.5 rounded-full border border-white/5 bg-white/5 px-2 py-1 font-medium text-white/55 outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/50"
                      >
                        <Timer size={11} aria-hidden="true" />
                        Provider {providerFirstOutputLabel}
                      </span>
                    ) : null}
                  </div>
                ) : null}
                <div
                  className="flex items-center gap-1.5 rounded-full border border-white/5 bg-white/5 px-2 py-1 backdrop-blur-sm"
                  ref={exportMenuRef}
                >
                  {message.versionCount && message.versionCount > 1 && (
                    <div className="mr-3 flex items-center gap-3 border-r border-white/10 pr-3">
                      <button
                        type="button"
                        aria-label="Show previous response version"
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
                      <span
                        aria-live="polite"
                        className="text-foreground font-mono text-[11px] tabular-nums"
                      >
                        {message.activeVersionIndex}
                        <span className="mx-1 opacity-30">/</span>
                        {message.versionCount}
                      </span>
                      <button
                        type="button"
                        aria-label="Show next response version"
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
                      ref={exportButtonRef}
                      aria-label="Export response"
                      aria-expanded={showExportMenu}
                      aria-controls={exportMenuId}
                      onClick={() => {
                        if (showExportMenu) {
                          closeExportMenu();
                        } else {
                          setExportMenuPosition(null);
                          setShowExportMenu(true);
                        }
                      }}
                      className={`flex h-7 w-7 items-center justify-center rounded-full text-white/40 transition-all duration-200 hover:bg-white/5 hover:text-white/80 ${
                        showExportMenu ? "bg-white/10 text-white" : ""
                      }`}
                    >
                      <Download size={12} />
                    </button>
                    {!showExportMenu ? (
                      <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                        <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                          Export
                        </div>
                      </div>
                    ) : null}

                    {showExportMenu
                      ? createPortal(
                          <div
                            id={exportMenuId}
                            ref={exportMenuOverlayRef}
                            role="group"
                            aria-label="Export format"
                            className="deepspace-export-menu border-border bg-background text-foreground fixed z-[1000] max-h-[calc(100dvh-1rem)] w-36 max-w-[calc(100vw-1rem)] overflow-y-auto rounded-xl border p-1 shadow-2xl"
                            style={{
                              top: exportMenuPosition?.top ?? 0,
                              left: exportMenuPosition?.left ?? 0,
                              visibility: exportMenuPosition ? "visible" : "hidden",
                            }}
                          >
                            <button
                              type="button"
                              onClick={() => {
                                exportToMarkdown(message.content);
                                closeExportMenu();
                              }}
                              className="text-foreground/80 hover:bg-surface-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition"
                            >
                              <FileCode size={12} className="text-cyan-400" /> Markdown
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                exportToPDF(message.content);
                                closeExportMenu();
                              }}
                              className="text-foreground/80 hover:bg-surface-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition"
                            >
                              <FileType size={12} className="text-rose-400" /> PDF
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                exportToDocx(message.content);
                                closeExportMenu();
                              }}
                              className="text-foreground/80 hover:bg-surface-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition"
                            >
                              <FileText size={12} className="text-indigo-400" /> DOCX
                            </button>
                          </div>,
                          document.body,
                        )
                      : null}
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
                        aria-label="Regenerate response"
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
    previous.isLast === next.isLast &&
    previous.isQueued === next.isQueued &&
    previous.canRetryFailedPrompt === next.canRetryFailedPrompt &&
    previous.isRetryingFailedPrompt === next.isRetryingFailedPrompt &&
    previous.isRetryActionDisabled === next.isRetryActionDisabled &&
    previous.onRetryFailedTurn === next.onRetryFailedTurn &&
    areMessageBubblesEqual(previous.message, next.message),
);

function areMessageBubblesEqual(previous: DeepSpaceMessage, next: DeepSpaceMessage): boolean {
  return (
    previous.clientRequestId === next.clientRequestId &&
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
    previous.agentSteps === next.agentSteps &&
    previous.timeline === next.timeline &&
    previous.blocks === next.blocks &&
    previous.structured === next.structured &&
    previous.mission === next.mission &&
    previous.compaction === next.compaction &&
    previous.memoryUsed === next.memoryUsed &&
    previous.artifacts === next.artifacts &&
    previous.mediaStatus === next.mediaStatus
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
  const responseMetricsHeight =
    message.metrics?.tokensPerSecond !== undefined ||
    message.metrics?.timeToFirstTokenMs !== undefined
      ? 24
      : 0;
  return baseHeight + estimatedLines * lineHeight + responseMetricsHeight;
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
  userName,
  onPromptSelect,
  onRegenerate = () => {},
  onStartEdit = () => {},
  onCancelEdit = () => {},
  onUpdateDraft = () => {},
  onSaveEdit = () => {},
  onActivateVersion = () => {},
  onResolveApproval,
  onSubmitUserQuestion,
  onRetryFailedTurn,
  retryableRequestIds = EMPTY_RETRYABLE_REQUEST_IDS,
  retryingRequestId = null,
  retryActionDisabled = false,
  queuedAssistantId = null,
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
  // While a response is streaming, the active message grows on every token.
  // Virtualization estimates would therefore change the spacer heights on
  // every render, making the viewport visibly jump and occasionally repaint
  // the active text. Keep the live turn in a stable, non-virtualized layout;
  // normal virtualization resumes as soon as generation finishes.
  const hasStreamingMessage = renderSourceMessages.some(
    (message) => message.status === "streaming",
  );
  // Agent turns contain variable-height thinking panels, tool payloads,
  // question cards, media, and markdown blocks. The lightweight height
  // estimator cannot safely represent those rows; virtualizing them causes
  // spacer drift while the user scrolls, making content appear to vanish.
  // Keep agentic turns in the normal flow and retain virtualization for
  // simple text-only history where the estimate is stable.
  const hasDynamicAgentContent = renderSourceMessages.some(
    (message) =>
      (message.agentSteps?.length ?? 0) > 0 ||
      (message.timeline?.length ?? 0) > 0 ||
      Boolean(message.thinkingContent?.trim()) ||
      (message.blocks?.length ?? 0) > 0 ||
      (message.artifacts?.length ?? 0) > 0,
  );
  const windowedMessages = useMemo(
    () =>
      buildWindowedMessages(
        renderSourceMessages,
        hasStreamingMessage || hasDynamicAgentContent ? null : scrollMetrics,
      ),
    [hasDynamicAgentContent, hasStreamingMessage, renderSourceMessages, scrollMetrics],
  );
  const shouldVirtualize = windowedMessages.visibleMessages.length < renderSourceMessages.length;
  const prefersReducedMotion = useReducedMotion();
  const [promptRotation, setPromptRotation] = useState(0);
  const [welcomeStatusRotation, setWelcomeStatusRotation] = useState(0);
  const promptPool = Array.from(new Set([...emptyPrompts, ...ROTATING_PROMPT_BANK]));
  const visiblePrompts = Array.from(
    { length: 4 },
    (_, index) => promptPool[(promptRotation + index) % promptPool.length],
  );

  useEffect(() => {
    if (messages.length > 0 || promptPool.length <= 4) return;
    const timer = window.setInterval(() => {
      setPromptRotation((current) => (current + 1) % promptPool.length);
    }, 6500);
    return () => window.clearInterval(timer);
  }, [messages.length, promptPool.length]);

  useEffect(() => {
    if (messages.length > 0 || prefersReducedMotion) return;
    const timer = window.setInterval(() => {
      setWelcomeStatusRotation((current) => (current + 1) % ROTATING_WELCOME_STATUSES.length);
    }, 4200);
    return () => window.clearInterval(timer);
  }, [messages.length, prefersReducedMotion]);

  if (messages.length === 0) {
    return (
      <div className="relative isolate flex h-full min-h-0 flex-col px-2 py-4">
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
          <Image
            src="/brand/deepspace-orbital-vortex.svg"
            alt=""
            aria-hidden="true"
            width={478}
            height={327}
            unoptimized
            className="absolute top-[62%] left-1/2 h-auto w-[min(58vw,28rem)] -translate-x-1/2 -translate-y-1/2 opacity-[0.05] grayscale select-none"
          />
        </div>
        <div className="relative z-10 mx-auto flex w-full max-w-5xl flex-1 flex-col">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="deepspace-welcome-title-accent text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">
                Welcome, {formatUserName(userName)}
              </h1>
              <div className="mt-3 grid min-h-[1.5rem] max-w-2xl">
                <span className="sr-only">DeepSpace is ready when you are.</span>
                <div
                  aria-hidden="true"
                  className="deepspace-welcome-status col-start-1 row-start-1"
                >
                  <span className="deepspace-welcome-status-orbit">
                    <span className="deepspace-welcome-status-dot" />
                    <span className="deepspace-welcome-status-dot deepspace-welcome-status-dot--secondary" />
                  </span>
                  <AnimatePresence initial={false} mode="wait">
                    <motion.span
                      key={welcomeStatusRotation}
                      initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -3 }}
                      transition={{
                        duration: prefersReducedMotion ? 0.12 : 0.3,
                        ease: PROMPT_MOTION_EASE,
                      }}
                      className="deepspace-welcome-status-label"
                    >
                      {
                        ROTATING_WELCOME_STATUSES[
                          welcomeStatusRotation % ROTATING_WELCOME_STATUSES.length
                        ]
                      }
                    </motion.span>
                  </AnimatePresence>
                </div>
              </div>
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
            <AnimatePresence mode="popLayout" initial={false}>
              {visiblePrompts.map((prompt, index) => {
                const motionVariant = getPromptMotionVariant(prompt, index, promptRotation);
                const cardDelay = prefersReducedMotion ? 0 : index * 0.06;

                return (
                  <motion.button
                    key={`${prompt}-${promptRotation}-${index}`}
                    type="button"
                    onClick={() => onPromptSelect(prompt)}
                    initial={prefersReducedMotion ? { opacity: 0 } : motionVariant.cardInitial}
                    animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
                    exit={prefersReducedMotion ? { opacity: 0 } : motionVariant.cardExit}
                    transition={{
                      duration: prefersReducedMotion ? 0.14 : 0.54,
                      delay: cardDelay,
                      ease: PROMPT_MOTION_EASE,
                    }}
                    className={`deepspace-empty-prompt deepspace-prompt-tone-${index} theme-panel-muted text-foreground/80 hover:border-primary/25 min-h-[7.5rem] rounded-[1rem] p-5 text-left text-[15px] leading-8 transition-colors`}
                  >
                    <motion.span
                      className="block"
                      initial={prefersReducedMotion ? { opacity: 0 } : motionVariant.textInitial}
                      animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
                      exit={prefersReducedMotion ? { opacity: 0 } : motionVariant.textExit}
                      transition={{
                        duration: prefersReducedMotion ? 0.12 : 0.42,
                        delay: prefersReducedMotion ? 0 : cardDelay + 0.045,
                        ease: PROMPT_MOTION_EASE,
                      }}
                    >
                      {prompt}
                    </motion.span>
                  </motion.button>
                );
              })}
            </AnimatePresence>
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
            onSubmitUserQuestion={onSubmitUserQuestion}
            onRetryFailedTurn={onRetryFailedTurn}
            canRetryFailedPrompt={
              message.status === "error" &&
              Boolean(message.clientRequestId && retryableRequestIds.has(message.clientRequestId))
            }
            isRetryingFailedPrompt={message.clientRequestId === retryingRequestId}
            isRetryActionDisabled={retryActionDisabled}
            isQueued={message.id === queuedAssistantId}
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
