"use client";

import { memo, useEffect, useRef, useState } from "react";
import { BrainCircuit } from "lucide-react";
import {
  CheckCircle2,
  CircleAlert,
  Eye,
  FlaskConical,
  ListChecks,
  LoaderCircle,
  MessageCircleQuestion,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";
import type { AgentStep, TimelineStep } from "../_lib/deepspace-stream";

const MAX_DETAIL_LENGTH = 2400;
const MAX_EXPANDED_DETAIL_LENGTH = 20000;

type PersistedTask = {
  id: string;
  content: string;
  status: string;
  active_form?: string;
};

type TaskProgress = {
  tasks: PersistedTask[];
  completed: number;
};

function truncateDetail(value: string, limit = MAX_DETAIL_LENGTH): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}\n… (${value.length - limit} more characters)`;
}

function sanitizeDetail(value: unknown, depth = 0): unknown {
  if (depth > 4) return "[nested value hidden]";
  if (typeof value === "string") {
    return value
      .replace(/Bearer\s+[A-Za-z0-9._~-]+/gi, "Bearer [redacted]")
      .replace(/(sk-[A-Za-z0-9_-]{12,})/g, "[redacted key]");
  }
  if (Array.isArray(value))
    return value.slice(0, 40).map((item) => sanitizeDetail(item, depth + 1));
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).reduce<Record<string, unknown>>(
      (result, [key, item]) => {
        if (
          /(token|secret|password|authorization|cookie|api[_-]?key|private[_-]?key|credential)/i.test(
            key,
          )
        ) {
          result[key] = "[redacted]";
        } else {
          result[key] = sanitizeDetail(item, depth + 1);
        }
        return result;
      },
      {},
    );
  }
  return value;
}

function humanizeKey(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function readableValue(value: unknown, indent = ""): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    if (!value.length) return "None";
    return value
      .map((item) => {
        const formatted = readableValue(item, `${indent}  `);
        return `${indent}• ${formatted.replace(/\n/g, `\n${indent}  `)}`;
      })
      .join("\n");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const formatted = readableValue(item, `${indent}  `);
        return `${indent}${humanizeKey(key)}: ${formatted.replace(/\n/g, `\n${indent}`)}`;
      })
      .join("\n");
  }
  return String(value);
}

function readablePartialStructuredText(value: string): string | null {
  if (!/^\s*[\[{]/.test(value)) return null;
  const fields = [...value.matchAll(/"([^"\\]+)"\s*:\s*(?:"([^"\\]*)|([-\d.]+)|(true|false|null))/g)];
  if (!fields.length) return "Collecting tool details…";
  return fields
    .map((field) => `${humanizeKey(field[1] ?? "Detail")}: ${field[2] ?? field[3] ?? field[4] ?? "—"}`)
    .join("\n");
}

function formatDetail(value: unknown, limit = MAX_DETAIL_LENGTH): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value === "string") {
    const sanitized = String(sanitizeDetail(value));
    try {
      return truncateDetail(readableValue(sanitizeDetail(JSON.parse(sanitized))), limit);
    } catch {
      return truncateDetail(readablePartialStructuredText(sanitized) ?? sanitized, limit);
    }
  }
  try {
    return truncateDetail(readableValue(sanitizeDetail(value)), limit);
  } catch {
    return "[detail unavailable]";
  }
}

function detailPreview(value: string | null): string | null {
  if (!value) return null;
  const firstLine = value
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);
  if (!firstLine) return null;
  return firstLine.length > 120 ? `${firstLine.slice(0, 117)}…` : firstLine;
}

function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} second${seconds === 1 ? "" : "s"}`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

function timelineDurationMs(timeline: TimelineStep[], now: number): number | null {
  const timestamps = timeline
    .flatMap((step) => [Date.parse(step.startedAt), Date.parse(step.completedAt ?? "")])
    .filter((timestamp) => Number.isFinite(timestamp));
  if (!timestamps.length) return null;
  const startedAt = Math.min(...timestamps);
  const completedAt = timeline.some((step) => step.status === "running") ? now : Math.max(...timestamps);
  return Math.max(0, completedAt - startedAt);
}

function taskProgressFromTimeline(timeline: TimelineStep[]): TaskProgress | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const step = timeline[index];
    if (
      !step?.toolName ||
      !["todo_write", "todo_read", "todo_mark", "todo_check"].includes(step.toolName)
    ) {
      continue;
    }
    try {
      const payload = JSON.parse(step.toolOutput || "") as Record<string, unknown>;
      const taskCheck =
        payload.task_check && typeof payload.task_check === "object"
          ? (payload.task_check as Record<string, unknown>)
          : payload;
      const rawTasks = taskCheck.tasks;
      if (!Array.isArray(rawTasks)) continue;
      const tasks = rawTasks
        .filter(
          (item): item is Record<string, unknown> => Boolean(item) && typeof item === "object",
        )
        .map((item) => ({
          id: String(item.id ?? ""),
          content: String(item.content ?? "Untitled task"),
          status: String(item.status ?? "pending"),
          active_form: typeof item.active_form === "string" ? item.active_form : undefined,
        }));
      if (!tasks.length) continue;
      return {
        tasks,
        completed:
          typeof taskCheck.completed_count === "number"
            ? taskCheck.completed_count
            : tasks.filter((task) => task.status === "completed").length,
      };
    } catch {
      // Tool output is displayed verbatim elsewhere; an invalid payload simply
      // cannot provide a reliable task-progress view.
    }
  }
  return null;
}

function TaskProgressCard({ progress }: { progress: TaskProgress }) {
  const total = progress.tasks.length;
  const completed = Math.min(Math.max(progress.completed, 0), total);
  const percentage = total ? Math.round((completed / total) * 100) : 0;

  return (
    <section
      aria-label="Verified task progress"
      data-testid="deepspace-task-progress"
      className="border-b border-cyan-300/15 pb-3"
    >
      <div className="flex items-center justify-between gap-3 text-[10px] font-semibold tracking-[0.12em] text-cyan-100/75 uppercase">
        <span>Verified task progress</span>
        <span className="normal-case tabular-nums">
          {completed}/{total} complete
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/35">
        <div
          className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400 transition-[width] duration-300"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <ol className="mt-2 space-y-1.5">
        {progress.tasks.map((task, index) => (
          <li
            key={task.id || `${task.content}-${index}`}
            className="flex items-start gap-2 text-[11px]"
          >
            <span
              className={
                task.status === "completed"
                  ? "text-emerald-300"
                  : task.status === "in_progress"
                    ? "text-cyan-300"
                    : "text-foreground/35"
              }
            >
              {task.status === "completed" ? "✓" : task.status === "in_progress" ? "◉" : "○"}
            </span>
            <span className="text-foreground/70 min-w-0 flex-1">
              {task.active_form || task.content}
            </span>
            <span className="text-foreground/35 shrink-0 text-[9px] uppercase">
              {task.status.replace(/_/g, " ")}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function stepTitle(step: AgentStep): string {
  if (step.type === "plan") return "Plan";
  if (step.type === "permission_request" || step.type === "ask_user_question")
    return "Approval or input required";
  if (step.type === "observing") return "Observation";
  if (step.type === "agent_testing") return "Testing";
  if (step.type === "agent_verifying") return "Verification";
  if (step.type === "agent_self_correct") return "Self-correction";
  if (step.type === "tool_error") return "Tool error";
  if (step.type === "tool_result") return "Tool result";
  return "Tool call";
}

function StepIcon({ step }: { step: AgentStep }) {
  if (step.status === "running")
    return <LoaderCircle size={13} className="animate-spin text-cyan-300" />;
  if (step.status === "awaiting_approval")
    return <ShieldCheck size={13} className="text-amber-300" />;
  if (step.status === "failed") return <XCircle size={13} className="text-red-300" />;
  if (step.type === "plan") return <ListChecks size={13} className="text-violet-300" />;
  if (step.type === "observing") return <Eye size={13} className="text-sky-300" />;
  if (step.type === "agent_testing" || step.type === "agent_verifying") {
    return <FlaskConical size={13} className="text-blue-300" />;
  }
  if (step.type === "permission_request" || step.type === "ask_user_question") {
    return <MessageCircleQuestion size={13} className="text-amber-300" />;
  }
  if (step.type === "tool_error") return <CircleAlert size={13} className="text-red-300" />;
  if (step.status === "completed") return <CheckCircle2 size={13} className="text-emerald-300" />;
  return <Wrench size={13} className="text-cyan-300" />;
}

const ActivityStep = memo(function ActivityStep({ step }: { step: AgentStep }) {
  const [outputOpen, setOutputOpen] = useState(step.status === "running");
  const input = formatDetail(step.toolInput ?? step.data?.tool_input);
  const output = formatDetail(
    step.toolOutput ?? step.plan ?? step.data?.message,
    MAX_EXPANDED_DETAIL_LENGTH,
  );
  const outputPreview = detailPreview(output);
  const toolName = step.toolName?.trim();
  const statusLabel =
    step.status === "awaiting_approval"
      ? "awaiting approval"
      : step.status === "running"
        ? "running"
        : step.status;

  return (
    <div
      className="border-b border-white/8 pb-3 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-200"
      data-testid="deepspace-activity-step"
    >
      <div className="text-foreground/65 flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] uppercase">
        <StepIcon step={step} />
        <span>{stepTitle(step)}</span>
        {toolName ? (
          <span className="text-foreground/85 min-w-0 truncate font-mono normal-case">
            {toolName}
          </span>
        ) : null}
        <span className="text-foreground/40 ml-auto shrink-0 text-[9px] tracking-normal normal-case">
          {statusLabel}
        </span>
      </div>
      {input ? (
        <details className="mt-2 border-t border-white/6 pt-1">
          <summary className="text-foreground/45 cursor-pointer py-1 text-[10px]">
            Input
          </summary>
          <pre className="text-foreground/60 max-h-48 overflow-auto py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
            {input}
          </pre>
        </details>
      ) : null}
      {output ? (
        <details
          open={outputOpen}
          onToggle={(event) => setOutputOpen(event.currentTarget.open)}
          className="mt-2 border-t border-white/6 pt-1"
        >
          <summary className="text-foreground/45 cursor-pointer py-1 text-[10px]">
            <span>Output / progress</span>
            {outputPreview ? <span className="ml-2 normal-case">— {outputPreview}</span> : null}
          </summary>
          <pre className="text-foreground/60 max-h-56 overflow-auto py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
            {output}
          </pre>
        </details>
      ) : null}
    </div>
  );
});

function TimelineIcon({ step }: { step: TimelineStep }) {
  if (step.status === "running") {
    return <LoaderCircle size={13} className="animate-spin text-cyan-300" />;
  }
  if (step.status === "awaiting_approval") {
    return <ShieldCheck size={13} className="text-amber-300" />;
  }
  if (step.status === "failed") return <XCircle size={13} className="text-red-300" />;
  if (step.type === "thinking") return <BrainCircuit size={13} className="text-violet-300" />;
  if (step.type === "model_message") return <MessageCircleQuestion size={13} className="text-cyan-300" />;
  if (step.type === "plan") return <ListChecks size={13} className="text-violet-300" />;
  if (step.type === "observation") return <Eye size={13} className="text-sky-300" />;
  if (step.type === "testing") return <FlaskConical size={13} className="text-blue-300" />;
  if (step.type === "permission") return <ShieldCheck size={13} className="text-amber-300" />;
  if (step.type === "error") return <CircleAlert size={13} className="text-red-300" />;
  return <Wrench size={13} className="text-cyan-300" />;
}

function timelineStatus(step: TimelineStep): string {
  if (step.status === "awaiting_approval") return "awaiting approval";
  if (step.status === "running") return "live";
  return step.status;
}

const TimelineEntry = memo(function TimelineEntry({
  step,
  index,
  isLast,
}: {
  step: TimelineStep;
  index: number;
  isLast: boolean;
}) {
  const [outputOpen, setOutputOpen] = useState(
    step.status === "running" || step.status === "failed",
  );
  const details = formatDetail(step.details);
  const inputStream = formatDetail(step.toolInputStream);
  const input = formatDetail(step.toolInput);
  const output = formatDetail(step.toolOutput, MAX_EXPANDED_DETAIL_LENGTH);
  const outputPreview = detailPreview(output);
  const toolName = step.toolName?.trim();

  return (
    <li
      className="relative pl-7 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-200"
      data-testid="deepspace-timeline-step"
    >
      {!isLast ? (
        <span className="absolute top-0 bottom-[-0.75rem] left-[0.4rem] w-px bg-white/8" />
      ) : null}
      <span className="absolute top-2 left-0 flex h-4 w-4 items-center justify-center rounded-full border border-white/10 bg-[#101713]">
        <TimelineIcon step={step} />
      </span>
      <div className="border-b border-white/8 pb-3">
        <div className="text-foreground/65 flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] uppercase">
          <span className="text-foreground/30 tabular-nums">
            {String(index + 1).padStart(2, "0")}
          </span>
          <span>{step.title}</span>
          {toolName ? (
            <span className="text-foreground/85 min-w-0 truncate font-mono normal-case">
              {toolName}
            </span>
          ) : null}
          <span className="text-foreground/40 ml-auto shrink-0 text-[9px] tracking-normal normal-case">
            {timelineStatus(step)}
          </span>
        </div>
        {details ? (
          <div
            className={`text-foreground/70 mt-2 ${
              step.type === "thinking"
                ? "max-h-64 overflow-auto overscroll-contain"
                : "leading-5 whitespace-pre-wrap"
            }`}
            data-thinking-scroll={step.type === "thinking" ? "true" : undefined}
          >
            {step.type === "thinking" || step.type === "model_message" ? (
              <DeepSpaceMarkdownRenderer
                content={details}
                streaming={step.status === "running"}
                compact
              />
            ) : (
              details
            )}
          </div>
        ) : null}
        {inputStream ? (
          <div className="mt-2 border-l border-cyan-300/25 pl-3 py-1">
            <div className="mb-1 text-[9px] font-semibold tracking-[0.12em] text-cyan-200/60 uppercase">
              Live tool arguments
            </div>
            <pre className="max-h-40 overflow-auto overscroll-contain text-[10px] leading-5 break-words whitespace-pre-wrap text-cyan-100/70">
              {inputStream}
            </pre>
          </div>
        ) : null}
        {input ? (
          <details className="mt-2 border-t border-white/6 pt-1">
            <summary className="text-foreground/45 cursor-pointer py-1 text-[10px]">
              Request details
            </summary>
            <pre className="text-foreground/60 max-h-48 overflow-auto overscroll-contain py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
              {input}
            </pre>
          </details>
        ) : null}
        {output ? (
          <details
            open={outputOpen}
            onToggle={(event) => setOutputOpen(event.currentTarget.open)}
            className="mt-2 border-t border-white/6 pt-1"
          >
            <summary className="text-foreground/45 cursor-pointer py-1 text-[10px]">
            <span>{step.status === "running" ? "Live tool output" : "Tool result"}</span>
            {outputPreview ? <span className="ml-2 normal-case">— {outputPreview}</span> : null}
            </summary>
            <pre className="text-foreground/60 max-h-56 overflow-auto overscroll-contain py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
              {output}
            </pre>
          </details>
        ) : null}
      </div>
    </li>
  );
});

export default function DeepSpaceThinkingPanel({
  content,
  isStreaming,
  agentSteps = [],
  timeline = [],
}: {
  content: string;
  isStreaming: boolean;
  agentSteps?: AgentStep[];
  timeline?: TimelineStep[];
}) {
  const [panelOpen, setPanelOpen] = useState(isStreaming);
  const wasStreaming = useRef(isStreaming);
  const [clock, setClock] = useState(() => Date.now());

  // Opening a newly active run should remain automatic, but completion must
  // not forcibly collapse the panel or override a user's expand/collapse
  // choice during reconciliation.
  useEffect(() => {
    if (isStreaming) {
      const timer = window.setTimeout(() => setPanelOpen(true), 0);
      wasStreaming.current = true;
      return () => window.clearTimeout(timer);
    }
    const timer = wasStreaming.current
      ? window.setTimeout(() => setPanelOpen(false), 0)
      : undefined;
    wasStreaming.current = false;
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [isStreaming]);

  useEffect(() => {
    if (!isStreaming) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isStreaming]);

  // Providers may emit argument fragments before the function name. The
  // backend labels that transient fragment `pending_tool`; it is not a
  // second execution and must not appear as a failed duplicate row.
  const activitySteps = agentSteps.filter(
    (step) => step.type !== "thinking" && step.toolName !== "pending_tool",
  );
  const orderedTimeline = timeline.filter((step) => step.toolName !== "pending_tool");
  // A completed turn is rehydrated from the persisted assistant metadata and
  // durable tool steps.  The durable step log intentionally contains tools,
  // not private model text, so do not hide the persisted thinking content just
  // because a tool timeline is present.  During live streaming, thinking is
  // represented as a timeline entry; avoid rendering it twice in that case.
  const hasThinkingTimeline = orderedTimeline.some(
    (step) => step.type === "thinking" && Boolean(step.details?.trim()),
  );
  const taskProgress = taskProgressFromTimeline(orderedTimeline);
  const elapsedMs = timelineDurationMs(orderedTimeline, clock);
  const durationLabel = elapsedMs === null ? null : formatElapsed(elapsedMs);
  if (
    !content.trim() &&
    activitySteps.length === 0 &&
    orderedTimeline.length === 0 &&
    !isStreaming
  ) {
    return null;
  }
  return (
    <details
      open={panelOpen}
      onToggle={(event) => setPanelOpen(event.currentTarget.open)}
      className="mb-4"
    >
      <summary className="text-foreground/50 flex cursor-pointer list-none items-center gap-2 border-b border-white/8 py-2 text-[11px] font-bold tracking-wider uppercase">
        <BrainCircuit size={13} className="text-primary/60" />
        <span>{isStreaming ? "Thinking & activity…" : "Thinking & activity"}</span>
        {durationLabel ? (
          <span className="text-foreground/35 ml-auto normal-case tracking-normal">
            {isStreaming ? `Working for ${durationLabel}` : `Worked for ${durationLabel}`}
          </span>
        ) : null}
      </summary>
      <div
        className="text-foreground/60 space-y-3 overscroll-contain py-3 text-xs"
        data-thinking-activity="true"
      >
        {taskProgress ? <TaskProgressCard progress={taskProgress} /> : null}
        {content.trim() && !hasThinkingTimeline ? (
          <div className="border-b border-white/8 pb-3" data-testid="deepspace-thinking-stream">
            <div className="text-foreground/45 mb-2 text-[10px] font-semibold tracking-[0.12em] uppercase">
              Model thinking
            </div>
            <DeepSpaceMarkdownRenderer content={content} streaming={isStreaming} compact />
          </div>
        ) : null}
        {orderedTimeline.length ? (
          <ol className="space-y-3" aria-label="Live agent timeline">
            {orderedTimeline.map((step, index) => (
              <TimelineEntry
                key={step.id}
                step={step}
                index={index}
                isLast={index === orderedTimeline.length - 1}
              />
            ))}
          </ol>
        ) : null}
        {!orderedTimeline.length && activitySteps.length ? (
          <div className="space-y-2" aria-label="Tool and agent activity">
            {activitySteps.map((step) => (
              <ActivityStep key={step.id} step={step} />
            ))}
          </div>
        ) : null}
        {isStreaming &&
        !content.trim() &&
        activitySteps.length === 0 &&
        orderedTimeline.length === 0 ? (
          <div className="text-foreground/45">Waiting for the model and tools…</div>
        ) : null}
      </div>
    </details>
  );
}
