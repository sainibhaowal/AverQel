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
import type { AgentStep } from "../_lib/deepspace-stream";

const MAX_DETAIL_LENGTH = 2400;

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

export default function DeepSpaceThinkingPanel({
  content,
  isStreaming,
  agentSteps = [],
}: {
  content: string;
  isStreaming: boolean;
  agentSteps?: AgentStep[];
}) {
  // Providers may emit argument fragments before the function name. The
  // backend labels that transient fragment `pending_tool`; it is not a
  // second execution and must not appear as a failed duplicate row.
  const activitySteps = agentSteps.filter(
    (step) => step.type !== "thinking" && step.toolName !== "pending_tool",
  );
  if (!content.trim() && activitySteps.length === 0 && !isStreaming) return null;
  return (
    <details open={isStreaming} className="mb-4 rounded-lg border border-white/5 bg-white/[0.02]">
      <summary className="text-foreground/50 flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11px] font-bold tracking-wider uppercase">
        <BrainCircuit size={13} className="text-primary/60" />
        {isStreaming ? "Thinking & activity…" : "Thinking & activity"}
      </summary>
      <div className="text-foreground/60 space-y-3 border-t border-white/5 px-4 py-3 text-xs">
        {content.trim() ? (
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
        {activitySteps.length ? (
          <div className="space-y-2" aria-label="Tool and agent activity">
            {activitySteps.map((step) => (
              <ActivityStep key={step.id} step={step} />
            ))}
          </div>
        ) : null}
        {isStreaming && !content.trim() && activitySteps.length === 0 ? (
          <div className="text-foreground/45">Waiting for the model and tools…</div>
        ) : null}
      </div>
    </details>
  );
}
