"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Code,
  Command,
  Database,
  Eye,
  FileCode,
  FileJson,
  FileText,
  Globe,
  HardDrive,
  HelpCircle,
  Layers,
  List,
  Mail,
  MessageSquare,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  Terminal,
  X,
  Zap,
  Bot,
  Brain,
  FolderOpen,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { TimelineStep, AgentPhase } from "../_lib/deepspace-stream";
import { getStepStatusLabel } from "../stateManagement";
import { InlineMarkdown } from "@/app/dashboard/query/_components/InlineMarkdown";
import { renderStructuredToolInput, renderStructuredToolOutput } from "./ToolRichPayload";

const TOOL_LABELS: Record<string, string> = {
  search_ecosystem_docs: "Search Docs",
  web_search: "Web Search",
  crawl_url: "Crawl URL",
  sync_connector: "Sync Connector",
  list_connectors: "List Connectors",
  get_connector_status: "Get Connector Status",
  gmail_search: "Gmail Search",
  gmail_read: "Gmail Read",
  gmail_send: "Gmail Send",
  gmail_manage: "Gmail Manage",
  calendar_list_events: "Calendar Events",
  calendar_find_free_slots: "Calendar Slots",
  calendar_create_event: "Calendar Create Event",
  notion_create_page: "Notion Create Page",
  notion_append_content: "Notion Append Content",
  list_dir: "List Directory",
  read_file: "Read File",
  write_file: "Write File",
  edit_file: "Edit File",
  bash: "Bash Command",
  run_command: "Run Command",
  glob: "Pattern Matching",
  grep: "Content Search",
  notebook_edit: "Notebook Edit",
  web_fetch: "Web Fetch",
  github_search: "GitHub Search",
  github_read_file: "GitHub Read File",
  drive_search: "Drive Search",
  drive_read_file: "Drive Read File",
  todo_write: "Todo Write",
  todo_read: "Todo Read",
  memory_write: "Memory Write",
  memory_read: "Memory Read",
  memory_search: "Memory Search",
  task: "Task",
  ask_user_question: "Clarification",
  bash_output: "Bash Output",
  kill_shell: "Kill Shell",
  enter_plan_mode: "Enter Plan Mode",
  exit_plan_mode: "Exit Plan Mode",
  skill: "Skill",
  slash_command: "Slash Command",
  data_analyze: "Data Analyze",
  document_convert: "Document Convert",
};

function getStepLabelAndIcon(step: TimelineStep): {
  icon: React.ReactNode;
  label: React.ReactNode;
} {
  const name = step.toolName || "";
  const input = step.toolInput || {};
  const isRunning = step.status === "running" || step.status === "awaiting_approval";
  const isClarificationStep = step.type === "permission" && step.title === "Clarification Needed";
  const showRawArguments =
    step.type !== "permission" && !!(step.toolInput && Object.keys(step.toolInput).length > 0);

  // 1. Thinking / Thought
  if (step.type === "thinking") {
    const statusLabel = getStepStatusLabel(step, { isStreaming: isRunning });
    return {
      icon: <Brain className="text-foreground/40 shrink-0" size={13} />,
      label: isRunning ? <span>{statusLabel}...</span> : <span>{statusLabel}</span>,
    };
  }

  // 2. Planning
  if (step.type === "plan") {
    return {
      icon: <Layers className="text-foreground/45 shrink-0" size={13} />,
      label: <span>Planning...</span>,
    };
  }

  // 3. Permission
  if (step.type === "permission") {
    const action = step.title === "Clarification Needed" ? "Clarification" : "Clearance";
    const toolInput = step.toolInput as { tier?: number } | undefined;
    const tier = step.data?.tier || toolInput?.tier || 2;
    const questions = Array.isArray(step.data?.questions)
      ? (step.data.questions as Array<{
          question?: string;
          options?: Array<{ label?: string; description?: string }>;
        }>)
      : [];
    const firstQuestion = questions[0]?.question?.trim();
    const firstOptions = questions[0]?.options ?? [];
    return {
      icon: <ShieldAlert className="shrink-0 animate-pulse text-amber-400" size={13} />,
      label: (
        <span className="flex flex-col gap-1.5 font-medium text-amber-400/90">
          <span className="flex flex-wrap items-center gap-1.5">
            <span>
              {action === "Clearance"
                ? `clearance required (tier ${tier})`
                : "clarification required"}
            </span>
            <span className="text-foreground/40 font-normal">
              {action === "Clearance" ? "Clearance requested to execute:" : "to run"}
            </span>
            <span className="font-mono font-bold text-amber-300">{name}</span>
          </span>
          {action === "Clarification" && firstQuestion ? (
            <span className="text-foreground/55 text-[10px] leading-relaxed normal-case">
              {firstQuestion}
              {firstOptions.length > 0 ? (
                <span className="text-foreground/35 block">
                  Options:{" "}
                  {firstOptions
                    .map((opt) => opt.label)
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              ) : null}
            </span>
          ) : null}
        </span>
      ),
    };
  }

  // 4. File Read
  if (
    name === "read_file" ||
    name === "file_read" ||
    name === "github_read_file" ||
    name === "drive_read_file"
  ) {
    const rawPath =
      typeof input.path === "string"
        ? input.path
        : typeof input.TargetFile === "string"
          ? input.TargetFile
          : "file";
    const filename = rawPath.split("/").pop() || rawPath;
    return {
      icon: (
        <FolderOpen
          className={`${step.status === "failed" ? "text-red-400" : "text-foreground/45"} shrink-0`}
          size={13}
        />
      ),
      label: isRunning ? (
        <span>
          Reading <span className="text-foreground/80 font-mono">{filename}</span>...
        </span>
      ) : step.status === "failed" ? (
        <span className="text-red-400/90">
          Failed to read <span className="font-mono text-red-300">{filename}</span>
        </span>
      ) : (
        <span>
          Read <span className="text-foreground/80 font-mono">{filename}</span>
        </span>
      ),
    };
  }

  // 5. File Write / Edit
  if (
    name === "edit_file" ||
    name === "file_edit" ||
    name === "write_file" ||
    name === "file_write"
  ) {
    const rawPath =
      typeof input.path === "string"
        ? input.path
        : typeof input.TargetFile === "string"
          ? input.TargetFile
          : "file";
    const filename = rawPath.split("/").pop() || rawPath;
    const additions = step.diffStats?.additions ?? 0;
    const deletions = step.diffStats?.deletions ?? 0;
    const stats =
      additions > 0 || deletions > 0 ? (
        <span className="ml-1 font-mono text-[10px] select-none">
          <span className="text-emerald-450">+{additions}</span>{" "}
          <span className="text-red-450">-{deletions}</span>
        </span>
      ) : null;

    return {
      icon: (
        <FileCode
          className={`${step.status === "failed" ? "text-red-400" : "text-foreground/45"} shrink-0`}
          size={13}
        />
      ),
      label: isRunning ? (
        <span>
          Editing <span className="text-foreground/80 font-mono">{filename}</span>...
        </span>
      ) : step.status === "failed" ? (
        <span className="text-red-400/90">
          Failed to edit <span className="font-mono text-red-300">{filename}</span>
        </span>
      ) : (
        <span>
          Edited <span className="text-foreground/80 font-mono">{filename}</span>
          {stats}
        </span>
      ),
    };
  }

  // 6. Searching / Globbing / Grepping
  if (
    name === "grep" ||
    name === "glob" ||
    name === "web_search" ||
    name === "github_search" ||
    name === "drive_search" ||
    name === "search_ecosystem_docs" ||
    name === "web_fetch"
  ) {
    const query =
      typeof input.pattern === "string"
        ? input.pattern
        : typeof input.query === "string"
          ? input.query
          : typeof input.url === "string"
            ? input.url
            : "";
    const searchLabel =
      name === "glob" ? "glob matches" : name === "grep" ? "grep search" : "search";
    return {
      icon: (
        <Search
          className={`${step.status === "failed" ? "text-red-400" : "text-foreground/45"} shrink-0`}
          size={13}
        />
      ),
      label: isRunning ? (
        <span>Searching...</span>
      ) : step.status === "failed" ? (
        <span className="text-red-400/90">
          Failed {searchLabel} <span className="text-red-300 italic">&quot;{query}&quot;</span>
        </span>
      ) : (
        <span>
          {name === "glob" ? "Glob matches" : name === "grep" ? "Grep search" : "Searched"}{" "}
          <span className="text-sky-400 italic">&quot;{query}&quot;</span>
        </span>
      ),
    };
  }

  // 7. Bash / Commands
  if (name === "bash" || name === "run_command") {
    const cmd = typeof input.command === "string" ? input.command : "";
    return {
      icon: (
        <Terminal
          className={`${step.status === "failed" ? "text-red-400" : "text-foreground/45"} shrink-0`}
          size={13}
        />
      ),
      label: isRunning ? (
        <span>
          Running{" "}
          <span className="text-foreground/80 rounded bg-white/5 px-1 py-0.5 font-mono text-[11px]">
            {cmd}
          </span>
          ...
        </span>
      ) : step.status === "failed" ? (
        <span className="text-red-400/90">
          Failed to run{" "}
          <span className="rounded bg-red-500/5 px-1 py-0.5 font-mono text-[11px] text-red-300">
            {cmd}
          </span>
        </span>
      ) : (
        <span>
          Ran{" "}
          <span className="text-foreground/80 rounded bg-white/5 px-1 py-0.5 font-mono text-[11px]">
            {cmd}
          </span>
        </span>
      ),
    };
  }

  // 8. Testing / Verification
  if (step.type === "testing") {
    const titleText = step.title || "Testing";
    return {
      icon: (
        <Activity
          className={`${step.status === "failed" ? "text-red-400" : "text-foreground/45"} shrink-0`}
          size={13}
        />
      ),
      label: isRunning ? (
        <span>{titleText}...</span>
      ) : step.status === "failed" ? (
        <span className="text-red-400/90">{titleText} failed</span>
      ) : (
        <span>{titleText} finished</span>
      ),
    };
  }

  // Fallback
  if (step.status === "failed") {
    return {
      icon: <ShieldAlert className="shrink-0 text-red-400" size={13} />,
      label: (
        <span className="text-red-400/90">
          Failed: {step.title || TOOL_LABELS[name] || name || "Execution Error"}
        </span>
      ),
    };
  }

  return {
    icon: <Bot className="text-foreground/45 shrink-0" size={13} />,
    label: <span>{step.title || TOOL_LABELS[name] || name || "Working..."}</span>,
  };
}

export default function AgentTimeline({
  timeline,
  isStreaming = false,
  onResume,
  onClarifyAnswer,
  hasContent = false,
}: {
  timeline: TimelineStep[];
  isStreaming?: boolean;
  onResume?: (stepId: string, toolId: string, approved: boolean) => void;
  onClarifyAnswer?: (prompt: string) => void;
  hasContent?: boolean;
}) {
  const [manualExpandedSteps, setManualExpandedSteps] = useState<Record<string, boolean>>({});
  const autoOpenStepIds = useMemo(
    () =>
      new Set(
        timeline.filter((step) => step.status === "awaiting_approval").map((step) => step.id),
      ),
    [timeline],
  );

  const toggleStep = (id: string) => {
    setManualExpandedSteps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const sortedSteps = useMemo(() => {
    return [...timeline].sort((a, b) => a.startedAt.localeCompare(b.startedAt));
  }, [timeline]);

  if (timeline.length === 0 && !isStreaming) return null;

  return (
    <div className="ml-1.5 flex flex-col gap-0.5 border-l border-white/5 px-1 py-1 pl-3 select-none">
      <AnimatePresence initial={false}>
        <div className="flex flex-col gap-1">
          {sortedSteps.map((step) => (
            <TimelineRow
              key={step.id}
              step={step}
              isExpanded={!!manualExpandedSteps[step.id] || autoOpenStepIds.has(step.id)}
              onToggle={() => toggleStep(step.id)}
              isStreaming={isStreaming}
              onResume={onResume}
              onClarifyAnswer={onClarifyAnswer}
            />
          ))}
        </div>

        {isStreaming && timeline.length === 0 && !hasContent && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-foreground/35 flex items-center gap-2 py-1 font-mono text-[12px] italic"
          >
            <RefreshCw size={12} className="animate-spin" />
            Initializing workflow...
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TimelineRow({
  step,
  isExpanded,
  onToggle,
  isStreaming,
  onResume,
  onClarifyAnswer,
}: {
  step: TimelineStep;
  isExpanded: boolean;
  onToggle: () => void;
  isStreaming: boolean;
  onResume?: (stepId: string, toolId: string, approved: boolean) => void;
  onClarifyAnswer?: (prompt: string) => void;
}) {
  const isRunning = step.status === "running" && isStreaming;
  const isAwaitingApproval = step.status === "awaiting_approval";
  const { icon, label } = getStepLabelAndIcon(step);
  const isClarificationStep = step.type === "permission" && step.title === "Clarification Needed";
  const showToolOutput = step.type !== "thinking" && !!step.toolOutput;
  const showRawArguments =
    step.type !== "permission" && !!(step.toolInput && Object.keys(step.toolInput).length > 0);
  const clarificationQuestions =
    isClarificationStep && Array.isArray(step.data?.questions)
      ? (step.data.questions as Array<{
          question?: string;
          options?: Array<{ label?: string; description?: string }>;
        }>)
      : [];
  const structuredToolInput =
    step.toolInput && Object.keys(step.toolInput).length > 0
      ? renderStructuredToolInput(step.toolName || "", step.toolInput)
      : null;
  const structuredToolOutput = step.toolOutput
    ? renderStructuredToolOutput(step.toolName || "", step.toolOutput)
    : null;

  const hasDetails = !!(
    step.details ||
    showToolOutput ||
    isAwaitingApproval ||
    isClarificationStep
  );

  return (
    <div className="flex flex-col py-0.5">
      <div
        onClick={hasDetails ? onToggle : undefined}
        className={`flex items-center gap-2 rounded px-1.5 py-0.5 text-[12.5px] leading-relaxed transition-colors ${
          hasDetails ? "cursor-pointer hover:bg-white/[0.02]" : "select-text"
        }`}
      >
        <div className="flex h-4 w-4 shrink-0 items-center justify-center">{icon}</div>

        <div className="text-foreground/60 flex min-w-0 flex-1 items-center gap-1.5 select-text">
          {label}
        </div>

        <div className="flex shrink-0 items-center gap-2 select-none">
          {isRunning && (
            <span className="inline-block min-w-[5.5rem] animate-pulse text-right font-mono text-[10px] font-bold text-sky-400 tabular-nums">
              running...
            </span>
          )}
          {hasDetails && (
            <span className="text-foreground/20 hover:text-foreground/45 pl-1 font-mono text-[9px] font-bold tracking-widest transition-colors">
              {isExpanded ? "▲" : "▼"}
            </span>
          )}
        </div>
      </div>

      <AnimatePresence>
        {isExpanded && hasDetails && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="ml-3 overflow-hidden border-l border-white/5 pl-6"
          >
            <div className="flex flex-col gap-2.5 py-2 pr-2">
              {step.details && (
                <div className="prose prose-invert text-foreground/45 max-w-none text-[12px] leading-relaxed">
                  <InlineMarkdown content={step.details} />
                </div>
              )}

              {isClarificationStep && clarificationQuestions.length > 0 && (
                <div className="flex flex-col gap-2">
                  <span className="text-foreground/20 text-[9px] font-bold tracking-wider uppercase">
                    clarification
                  </span>
                  {clarificationQuestions.map((question, idx) => (
                    <div
                      key={idx}
                      className="space-y-1.5 rounded-lg border border-white/5 bg-black/20 p-2.5"
                    >
                      {question.question ? (
                        <p className="text-foreground/75 text-[11px] leading-relaxed">
                          {question.question}
                        </p>
                      ) : null}
                      {(question.options ?? []).length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {question.options?.map((option, optionIdx) => (
                            <button
                              key={optionIdx}
                              type="button"
                              onClick={() => {
                                const responseText = [option.label, option.description]
                                  .filter(Boolean)
                                  .join(" - ");
                                if (onClarifyAnswer) {
                                  onClarifyAnswer(responseText);
                                }
                              }}
                              className="text-foreground/55 hover:border-primary/25 hover:text-primary cursor-pointer rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-left text-[10px] font-medium transition-colors"
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}

              {showRawArguments && (
                <div className="flex flex-col gap-1">
                  <span className="text-foreground/20 text-[9px] font-bold tracking-wider uppercase">
                    arguments
                  </span>
                  {structuredToolInput ?? (
                    <pre className="overflow-x-auto rounded border border-white/5 bg-black/25 p-2 font-mono text-[11px] leading-relaxed text-sky-400/70">
                      {JSON.stringify(step.toolInput, null, 2)}
                    </pre>
                  )}
                </div>
              )}

              {showToolOutput && (
                <div className="flex flex-col gap-1">
                  <span className="text-foreground/20 text-[9px] font-bold tracking-wider uppercase">
                    output
                  </span>
                  {structuredToolOutput ?? (
                    <div className="prose prose-invert text-foreground/45 custom-scrollbar max-h-[250px] max-w-none overflow-x-auto overflow-y-auto rounded border border-white/5 bg-black/25 p-2 text-[11px] leading-relaxed">
                      <InlineMarkdown content={step.toolOutput ?? ""} />
                    </div>
                  )}
                </div>
              )}

              {isAwaitingApproval && onResume && (
                <div className="flex max-w-xs items-center gap-2 border-t border-white/5 pt-1.5 select-none">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onResume(step.stepId, step.toolId || "", true);
                    }}
                    className="flex-1 cursor-pointer rounded border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-[10px] font-bold tracking-widest text-emerald-400 uppercase transition-colors hover:bg-emerald-500/20"
                  >
                    Approve
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onResume(step.stepId, step.toolId || "", false);
                    }}
                    className="flex-1 cursor-pointer rounded border border-red-500/25 bg-red-500/10 px-3 py-1 text-[10px] font-bold tracking-widest text-red-400 uppercase transition-colors hover:bg-red-500/20"
                  >
                    Deny
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
