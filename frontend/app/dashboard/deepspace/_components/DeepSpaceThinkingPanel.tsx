"use client";

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

function formatDetail(value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value === "string") return truncateDetail(String(sanitizeDetail(value)));
  try {
    return truncateDetail(JSON.stringify(sanitizeDetail(value), null, 2));
  } catch {
    return "[detail unavailable]";
  }
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
      className="rounded-lg border border-cyan-300/15 bg-cyan-300/[0.035] px-3 py-2.5"
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

function ActivityStep({ step }: { step: AgentStep }) {
  const input = formatDetail(step.toolInput ?? step.data?.tool_input);
  const output = formatDetail(step.toolOutput ?? step.plan ?? step.data?.message);
  const toolName = step.toolName?.trim();
  const statusLabel =
    step.status === "awaiting_approval"
      ? "awaiting approval"
      : step.status === "running"
        ? "running"
        : step.status;

  return (
    <div
      className="rounded-lg border border-white/8 bg-black/15 px-3 py-2"
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
        <details className="mt-2 rounded border border-white/6 bg-black/15">
          <summary className="text-foreground/45 cursor-pointer px-2 py-1 text-[10px]">
            Input
          </summary>
          <pre className="text-foreground/60 max-h-48 overflow-auto border-t border-white/6 px-2 py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
            {input}
          </pre>
        </details>
      ) : null}
      {output ? (
        <details
          open={step.status === "running"}
          className="mt-2 rounded border border-white/6 bg-black/15"
        >
          <summary className="text-foreground/45 cursor-pointer px-2 py-1 text-[10px]">
            Output / progress
          </summary>
          <pre className="text-foreground/60 max-h-56 overflow-auto border-t border-white/6 px-2 py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
            {output}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function TimelineIcon({ step }: { step: TimelineStep }) {
  if (step.status === "running") {
    return <LoaderCircle size={13} className="animate-spin text-cyan-300" />;
  }
  if (step.status === "awaiting_approval") {
    return <ShieldCheck size={13} className="text-amber-300" />;
  }
  if (step.status === "failed") return <XCircle size={13} className="text-red-300" />;
  if (step.type === "thinking") return <BrainCircuit size={13} className="text-violet-300" />;
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

function TimelineEntry({
  step,
  index,
  isLast,
}: {
  step: TimelineStep;
  index: number;
  isLast: boolean;
}) {
  const details = formatDetail(step.details);
  const inputStream = formatDetail(step.toolInputStream);
  const input = formatDetail(step.toolInput);
  const output = formatDetail(step.toolOutput);
  const toolName = step.toolName?.trim();

  return (
    <li className="relative pl-7" data-testid="deepspace-timeline-step">
      {!isLast ? (
        <span className="absolute top-0 bottom-[-0.75rem] left-[0.4rem] w-px bg-white/8" />
      ) : null}
      <span className="absolute top-2 left-0 flex h-4 w-4 items-center justify-center rounded-full border border-white/10 bg-[#101713]">
        <TimelineIcon step={step} />
      </span>
      <div className="rounded-lg border border-white/8 bg-black/15 px-3 py-2.5">
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
            className={`text-foreground/70 mt-2 whitespace-pre-wrap ${
              step.type === "thinking" ? "max-h-64 overflow-auto leading-6" : "leading-5"
            }`}
          >
            {details}
          </div>
        ) : null}
        {inputStream ? (
          <div className="mt-2 rounded border border-cyan-300/10 bg-cyan-300/[0.03] px-2 py-2">
            <div className="mb-1 text-[9px] font-semibold tracking-[0.12em] text-cyan-200/60 uppercase">
              Live tool arguments
            </div>
            <pre className="max-h-40 overflow-auto text-[10px] leading-5 break-words whitespace-pre-wrap text-cyan-100/70">
              {inputStream}
            </pre>
          </div>
        ) : null}
        {input ? (
          <details className="mt-2 rounded border border-white/6 bg-black/15">
            <summary className="text-foreground/45 cursor-pointer px-2 py-1 text-[10px]">
              Request details
            </summary>
            <pre className="text-foreground/60 max-h-48 overflow-auto border-t border-white/6 px-2 py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
              {input}
            </pre>
          </details>
        ) : null}
        {output ? (
          <details
            open={step.status === "running" || step.status === "failed"}
            className="mt-2 rounded border border-white/6 bg-black/15"
          >
            <summary className="text-foreground/45 cursor-pointer px-2 py-1 text-[10px]">
              {step.status === "running" ? "Live tool output" : "Tool result"}
            </summary>
            <pre className="text-foreground/60 max-h-56 overflow-auto border-t border-white/6 px-2 py-2 text-[10px] leading-5 break-words whitespace-pre-wrap">
              {output}
            </pre>
          </details>
        ) : null}
      </div>
    </li>
  );
}

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
  // Providers may emit argument fragments before the function name. The
  // backend labels that transient fragment `pending_tool`; it is not a
  // second execution and must not appear as a failed duplicate row.
  const activitySteps = agentSteps.filter(
    (step) => step.type !== "thinking" && step.toolName !== "pending_tool",
  );
  const orderedTimeline = timeline.filter((step) => step.toolName !== "pending_tool");
  const taskProgress = taskProgressFromTimeline(orderedTimeline);
  if (
    !content.trim() &&
    activitySteps.length === 0 &&
    orderedTimeline.length === 0 &&
    !isStreaming
  ) {
    return null;
  }
  return (
    <details open={isStreaming} className="mb-4 rounded-lg border border-white/5 bg-white/[0.02]">
      <summary className="text-foreground/50 flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11px] font-bold tracking-wider uppercase">
        <BrainCircuit size={13} className="text-primary/60" />
        {isStreaming ? "Thinking & activity…" : "Thinking & activity"}
      </summary>
      <div className="text-foreground/60 space-y-3 border-t border-white/5 px-4 py-3 text-xs">
        {taskProgress ? <TaskProgressCard progress={taskProgress} /> : null}
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
        ) : content.trim() ? (
          <div
            className="rounded-lg border border-white/8 bg-black/10 px-3 py-2"
            data-testid="deepspace-thinking-stream"
          >
            <div className="text-foreground/45 mb-2 text-[10px] font-semibold tracking-[0.12em] uppercase">
              Model thinking
            </div>
            <DeepSpaceMarkdownRenderer content={content} streaming={isStreaming} />
          </div>
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
