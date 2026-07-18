"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Globe,
  Search,
  ShieldAlert,
  Clock,
  Mail,
  FileText,
  Zap,
  AlertTriangle,
  Github,
  HardDrive,
  RefreshCw,
  List,
  Terminal,
  Database,
  CheckSquare,
  MessageSquare,
  Layers,
  Code,
  Sparkles,
  Command,
  Activity,
  HelpCircle,
  Eye,
  FileCode,
  FileJson,
  FolderOpen,
  X,
} from "lucide-react";
import { useMemo, useState, useEffect } from "react";

import type { AgentStep, TimelineStep } from "../_lib/deepspace-stream";
import { getStepStatusLabel } from "../stateManagement";
import { TOOL_LABELS } from "../_lib/constants";
import type { MessageMetrics } from "@/app/dashboard/query/_lib/stream-protocol";
import { InlineMarkdown } from "@/app/dashboard/query/_components/InlineMarkdown";
import { renderStructuredToolInput, renderStructuredToolOutput } from "./ToolRichPayload";
import { estimateTokens } from "@/app/dashboard/query/_lib/stream-protocol";
import AgentTimeline from "./AgentTimeline";

type ClarificationOption = {
  label: string;
  description?: string;
};

type ClarificationQuestion = {
  header: string;
  question: string;
  options?: ClarificationOption[];
};

type DiffLine = {
  type: "added" | "removed" | "unchanged";
  text: string;
};

const TOOL_ICONS: Record<string, React.ReactNode> = {
  search_ecosystem_docs: <Search size={12} />,
  web_search: <Globe size={12} />,
  crawl_url: <RefreshCw size={12} />,
  sync_connector: <RefreshCw size={12} />,
  list_connectors: <List size={12} />,
  get_connector_status: <Zap size={12} />,
  gmail_search: <Mail size={12} />,
  gmail_read: <Mail size={12} />,
  gmail_send: <Mail size={12} />,
  gmail_manage: <Mail size={12} />,
  calendar_list_events: <Clock size={12} />,
  calendar_find_free_slots: <Clock size={12} />,
  calendar_create_event: <Clock size={12} />,
  notion_create_page: <FileText size={12} />,
  notion_append_content: <FileText size={12} />,
  list_dir: <List size={12} />,
  read_file: <FileText size={12} />,
  write_file: <FileText size={12} />,
  edit_file: <Code size={12} />,
  bash: <Terminal size={12} />,
  run_command: <Terminal size={12} />,
  glob: <Search size={12} />,
  grep: <Search size={12} />,
  notebook_edit: <Layers size={12} />,
  web_fetch: <Globe size={12} />,
  github_search: <Github size={12} />,
  github_read_file: <Github size={12} />,
  drive_search: <HardDrive size={12} />,
  drive_read_file: <HardDrive size={12} />,
  todo_write: <CheckSquare size={12} />,
  todo_read: <CheckSquare size={12} />,
  memory_write: <Database size={12} />,
  memory_read: <Database size={12} />,
  memory_search: <Database size={12} />,
  task: <Sparkles size={12} />,
  ask_user_question: <MessageSquare size={12} />,
  bash_output: <Terminal size={12} />,
  kill_shell: <Terminal size={12} />,
  enter_plan_mode: <Layers size={12} />,
  exit_plan_mode: <Zap size={12} />,
  skill: <Sparkles size={12} />,
  slash_command: <Command size={12} />,
  data_analyze: <Activity size={12} />,
  document_convert: <RefreshCw size={12} />,
  observing: <Eye size={12} />,
};

function parseTerminalLines(output: string): Array<{
  id: string;
  kind: "stderr" | "system" | "stdout";
  text: string;
}> {
  return output.split("\n").map((line, index) => {
    if (line.startsWith("[stderr]")) {
      return { id: `stderr-${index}`, kind: "stderr" as const, text: line.slice(8).trimStart() };
    }
    if (line.startsWith("[system]")) {
      return { id: `system-${index}`, kind: "system" as const, text: line.slice(8).trimStart() };
    }
    return { id: `stdout-${index}`, kind: "stdout" as const, text: line };
  });
}

type TurnGroup = {
  turnIndex: number;
  status: "idle" | "thinking" | "executing" | "completed" | "failed" | "awaiting_approval";
  steps: AgentStep[];
  title: string;
};

function getFileIconAndColor(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "py":
      return {
        icon: <FileCode className="text-emerald-450 opacity-70" size={12} />,
        labelColor: "text-emerald-400",
      };
    case "ts":
    case "tsx":
      return {
        icon: <FileCode className="text-sky-450 opacity-70" size={12} />,
        labelColor: "text-sky-400",
      };
    case "js":
    case "jsx":
      return {
        icon: <FileCode className="text-yellow-450 opacity-70" size={12} />,
        labelColor: "text-yellow-450",
      };
    case "json":
      return {
        icon: <FileJson className="text-amber-450 opacity-70" size={12} />,
        labelColor: "text-amber-450",
      };
    case "md":
    case "txt":
      return {
        icon: <FileText className="text-foreground/40" size={12} />,
        labelColor: "text-foreground/40",
      };
    default:
      return {
        icon: <FileText className="text-foreground/30" size={12} />,
        labelColor: "text-foreground/30",
      };
  }
}

function getStepActivityRow(step: AgentStep) {
  const name = step.toolName || "";
  const input = step.toolInput || {};

  if (
    step.type === "agent_testing" ||
    step.type === "agent_verifying" ||
    step.type === "agent_self_correct"
  ) {
    const formattedTool = name ? (TOOL_LABELS[name] ?? name.replace(/_/g, " ")) : "agent step";
    const action =
      step.type === "agent_testing"
        ? "Testing"
        : step.type === "agent_verifying"
          ? "Verifying"
          : "Self-correcting";
    return (
      <span className="inline-flex items-center gap-1">
        <span className="text-foreground/40 font-medium">{action}</span>
        <span className="text-foreground/80 font-bold">{formattedTool}</span>
      </span>
    );
  }

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

    return (
      <span className="inline-flex items-center gap-1">
        <span className="text-foreground/40 font-medium">Writing</span>
        <span className="text-foreground/80 font-bold">{filename}</span>
        {(additions > 0 || deletions > 0) && (
          <span className="ml-1 text-[9px] font-bold">
            <span className="text-emerald-455">+{additions}</span>{" "}
            <span className="text-red-455">-{deletions}</span>
          </span>
        )}
      </span>
    );
  }

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
    const start = input.StartLine || input.offset || 1;
    const end = input.EndLine || (input.limit ? Number(start) + Number(input.limit) - 1 : null);
    const rangeStr = end ? `#L${start}-${end}` : `#L${start}`;

    return (
      <span className="inline-flex items-center gap-1">
        <span className="text-foreground/40 font-medium">Reading</span>
        <span className="text-foreground/80 font-bold">{filename}</span>
        <span className="text-foreground/30 text-[9px] font-bold">{rangeStr}</span>
      </span>
    );
  }

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
            : "search";
    return (
      <span className="inline-flex items-center gap-1">
        <span className="text-foreground/40 font-medium">Searching</span>
        <span className="text-sky-350 max-w-[200px] truncate font-bold italic">
          &quot;{query}&quot;
        </span>
      </span>
    );
  }

  if (name === "list_dir" || name === "file_list") {
    const directory =
      typeof input.directory === "string"
        ? input.directory
        : typeof input.DirectoryPath === "string"
          ? input.DirectoryPath
          : ".";
    const dirname = directory.split("/").pop() || directory;

    return (
      <span className="inline-flex items-center gap-1">
        <span className="text-foreground/40 font-medium">Listing</span>
        <span className="text-foreground/80 font-bold">{dirname}</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-foreground/40 font-medium">Running</span>
      <span className="text-foreground/80 font-mono font-bold">{name}</span>
    </span>
  );
}

export default function AgentStepPanel({
  steps,
  timeline,
  isStreaming = true,
  metrics,
  onResume,
  onClarifyAnswer,
  hasContent = false,
}: {
  steps: AgentStep[];
  timeline?: TimelineStep[];
  isStreaming?: boolean;
  metrics?: MessageMetrics;
  onResume?: (stepId: string, toolCallId: string, approved: boolean) => void;
  onClarifyAnswer?: (prompt: string) => void;
  hasContent?: boolean;
}) {
  const visibleSteps = useMemo(() => steps ?? [], [steps]);
  const [isOpen, setIsOpen] = useState(true);
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [isReviewOpen, setIsReviewOpen] = useState(false);
  const [selectedReviewFile, setSelectedReviewFile] = useState<string | null>(null);

  // Thinking banner states
  const [thinkingTimers, setThinkingTimers] = useState<Record<string, number>>({});
  const [thinkingExpandedStates, setThinkingExpandedStates] = useState<Record<string, boolean>>({});

  // Active thinking steps finder
  const activeThinkingSteps = useMemo(() => {
    return visibleSteps.filter(
      (s) =>
        s.type === "thinking" ||
        s.toolName === "thinking" ||
        (s.toolName === "slash_command" &&
          (s.toolInput as { command?: string })?.command === "/think"),
    );
  }, [visibleSteps]);

  useEffect(() => {
    const autoOpenSteps = visibleSteps.filter(
      (step) =>
        step.status === "awaiting_approval" ||
        step.type === "ask_user_question" ||
        step.type === "permission_request",
    );

    if (autoOpenSteps.length === 0) {
      return;
    }

    setThinkingExpandedStates((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const step of autoOpenSteps) {
        if (!next[step.id]) {
          next[step.id] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [visibleSteps]);

  // Live timer for all active/running thinking steps inline
  useEffect(() => {
    const running = activeThinkingSteps.filter((s) => s.status === "running" && isStreaming);
    if (running.length === 0) return;

    const interval = setInterval(() => {
      setThinkingTimers((prev) => {
        const next = { ...prev };
        running.forEach((step) => {
          const start = step.startedAt ? new Date(step.startedAt).getTime() : Date.now();
          next[step.id] = Math.max(0, Math.round((Date.now() - start) / 1000));
        });
        return next;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [activeThinkingSteps, isStreaming]);

  const modifiedFiles = useMemo(() => {
    const filesMap: Record<
      string,
      { path: string; additions: number; deletions: number; diffLines?: DiffLine[] }
    > = {};
    visibleSteps.forEach((step) => {
      if ((step.type === "tool_start" || step.type === "tool_result") && step.diffStats) {
        const path = step.diffStats.path;
        if (!filesMap[path]) {
          filesMap[path] = {
            path,
            additions: 0,
            deletions: 0,
            diffLines: step.diffStats.diffLines,
          };
        }
        filesMap[path].additions += step.diffStats.additions;
        filesMap[path].deletions += step.diffStats.deletions;
        filesMap[path].diffLines = step.diffStats.diffLines;
      }
    });
    return Object.values(filesMap);
  }, [visibleSteps]);

  const totalAdditions = useMemo(
    () => modifiedFiles.reduce((acc, f) => acc + f.additions, 0),
    [modifiedFiles],
  );
  const totalDeletions = useMemo(
    () => modifiedFiles.reduce((acc, f) => acc + f.deletions, 0),
    [modifiedFiles],
  );

  useEffect(() => {
    if (modifiedFiles.length > 0 && !selectedReviewFile) {
      setSelectedReviewFile(modifiedFiles[0].path);
    }
  }, [modifiedFiles, selectedReviewFile]);

  const flatSteps = useMemo(() => {
    const list = [...visibleSteps].filter((step) => {
      // Exclude step boundary events from the compact execution trace.
      if (step.type === "step_start" || step.type === "step_finish") return false;

      return true;
    });

    if (isStreaming && list.length === 0 && !hasContent) {
      list.push({
        id: "synthetic-initial",
        type: "observing",
        status: "running",
        plan: "Initializing agent...",
        startedAt: new Date().toISOString(),
      });
    }
    return list;
  }, [visibleSteps, isStreaming, hasContent]);

  const isActive = useMemo(() => {
    if (!isStreaming) return false;
    if (flatSteps.length === 0) return true;
    const latest = flatSteps[flatSteps.length - 1];
    return latest.status === "running" || latest.status === "awaiting_approval";
  }, [flatSteps, isStreaming]);

  const [spinnerIdx, setSpinnerIdx] = useState(0);
  useEffect(() => {
    if (!isActive) return;
    const timer = setInterval(() => {
      setSpinnerIdx((prev) => (prev + 1) % 4);
    }, 150);
    return () => clearInterval(timer);
  }, [isActive]);

  const spinner = ["⠋", "⠙", "⠹", "⠸"][spinnerIdx];

  const stepEntries = useMemo(() => {
    return flatSteps.flatMap((step, idx) => {
      const nodes: React.ReactNode[] = [];

      const isDestructive = Number((step.data as { tier?: number })?.tier ?? 3) === 4;
      const tierNum = Number((step.data as { tier?: number })?.tier ?? 3);
      const isExpanded = !!expandedSteps[step.id];
      const isRunning = step.status === "running" && isStreaming;
      const stepVariants = {
        initial: { opacity: 0, x: -8, filter: "blur(4px)" },
        animate: { opacity: 1, x: 0, filter: "blur(0px)" },
        exit: { opacity: 0, transition: { duration: 0.1 } },
      };

      if (step.type === "plan" && step.plan) {
        nodes.push(
          <motion.div
            key={step.id || `plan-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className="text-foreground/50 flex items-start gap-2 leading-relaxed"
          >
            <span className="text-primary/70 shrink-0 font-bold">➔ planning:</span>
            <div className="prose prose-invert text-foreground/50 max-w-none min-w-0 flex-1">
              <InlineMarkdown content={step.plan} />
            </div>
          </motion.div>,
        );
        return nodes;
      }

      if (step.type === "thinking") {
        const isStepExpanded =
          thinkingExpandedStates[step.id] ?? (step.status === "running" && isStreaming);
        const timerSeconds = thinkingTimers[step.id] ?? 0;
        const textContent = step.plan || step.toolOutput || "";
        const tokenCount = estimateTokens(textContent);
        const isStepActive = step.status === "running" && isStreaming;
        const stageLabel = isStepActive
          ? "Thinking"
          : getStepStatusLabel(step, { isStreaming: false, timerSeconds });

        nodes.push(
          <motion.div
            key={step.id || `think-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className="mb-2 overflow-hidden rounded-lg border border-white/5 bg-white/[0.02] transition-colors duration-200"
          >
            <button
              type="button"
              onClick={() =>
                setThinkingExpandedStates((prev) => ({
                  ...prev,
                  [step.id]: !isStepExpanded,
                }))
              }
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left font-mono transition-colors hover:bg-white/[0.03]"
            >
              <ChevronDown
                size={12}
                className={`text-foreground/30 transition-transform duration-200 ${
                  isStepExpanded ? "" : "-rotate-90"
                }`}
              />
              <div className="flex items-center gap-2">
                <Sparkles size={11} className="text-primary/60" />
                <span className="text-foreground/50 text-[10px] font-bold tracking-wider whitespace-nowrap uppercase">
                  {stageLabel}
                </span>
              </div>
              {timerSeconds > 0 && (
                <span className="text-foreground/35 ml-1 inline-block min-w-[4rem] text-right font-mono text-[9px] tabular-nums">
                  {timerSeconds}s
                </span>
              )}
              {tokenCount > 0 && (
                <span className="text-emerald-450/70 ml-1.5 font-mono text-[9px]">
                  ({tokenCount} tokens)
                </span>
              )}
              {isStepActive && (
                <motion.div
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ repeat: Infinity, duration: 1.5 }}
                  className="h-1.2 w-1.2 bg-primary ml-auto rounded-full shadow-[0_0_8px_rgba(var(--primary),0.8)]"
                />
              )}
            </button>

            <AnimatePresence initial={false}>
              {isStepExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.12, ease: "easeOut" }}
                >
                  <div className="min-h-[88px] border-t border-white/5 bg-black/10 px-4 py-3">
                    <div className="prose prose-invert text-foreground/60 max-w-none text-[11.5px] leading-relaxed">
                      <InlineMarkdown content={textContent} />
                      {isStepActive && (
                        <motion.span
                          animate={{ opacity: [1, 0, 1] }}
                          transition={{ repeat: Infinity, duration: 0.8 }}
                          className="bg-primary/40 ml-1 inline-block h-3.5 w-1.5 align-middle"
                        />
                      )}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>,
        );
        return nodes;
      }

      if (step.type === "observing") {
        nodes.push(
          <motion.div
            key={step.id || `obs-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className="flex items-start gap-2 leading-relaxed whitespace-pre-wrap text-cyan-400/70"
          >
            <span className="shrink-0 font-bold text-cyan-400">➔ observation:</span>
            <span>{step.plan || step.toolOutput}</span>
          </motion.div>,
        );
        return nodes;
      }

      if (step.type === "tool_error") {
        nodes.push(
          <motion.div
            key={step.id || `err-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className="flex items-start gap-2 leading-relaxed whitespace-pre-wrap text-red-400/80"
          >
            <span className="shrink-0 font-bold text-red-400">➔ error:</span>
            <span>{step.toolOutput || step.plan || "Tool execution failed"}</span>
          </motion.div>,
        );
        return nodes;
      }

      if (step.type === "permission_request") {
        nodes.push(
          <motion.div
            key={step.id || `perm-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className={`mt-2 border p-3 shadow-lg select-none ${
              isDestructive
                ? "border-red-500/20 bg-red-500/5 text-red-200 shadow-red-500/5"
                : "border-amber-500/20 bg-amber-500/5 text-amber-200 shadow-amber-500/5"
            }`}
          >
            <div className="flex items-start gap-2">
              <ShieldAlert
                size={14}
                className={
                  isDestructive
                    ? "mt-0.5 animate-pulse text-red-400"
                    : "mt-0.5 animate-pulse text-amber-400"
                }
              />
              <div className="flex-1 space-y-2">
                <p className="text-[10px] font-bold tracking-wider uppercase">
                  clearance required (tier {tierNum})
                </p>
                <p className="text-[9.5px] leading-relaxed italic opacity-70">
                  Clearance requested to execute: <span className="font-bold">{step.toolName}</span>
                </p>

                {isDestructive && (
                  <div className="mt-1.5 flex flex-col gap-1">
                    <label className="text-[8.5px] font-bold tracking-wider text-red-400/60 uppercase">
                      Type &quot;DELETE&quot; to authorize
                    </label>
                    <input
                      type="text"
                      value={deleteConfirmation}
                      placeholder="Type DELETE..."
                      className="rounded border border-red-500/30 bg-black/40 px-2 py-1 font-mono text-[9.5px] text-red-400 transition-colors outline-none focus:border-red-500/60"
                      onChange={(e) => setDeleteConfirmation(e.target.value.toUpperCase())}
                    />
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    onClick={() =>
                      handleDecision(String(step.step_id), String(step.tool_id), false)
                    }
                    className="text-foreground/50 hover:text-foreground/80 cursor-pointer rounded border border-white/5 bg-white/5 px-2.5 py-1 text-[9.5px] font-bold transition hover:bg-white/10"
                  >
                    Decline
                  </button>
                  <button
                    onClick={() => handleDecision(String(step.step_id), String(step.tool_id), true)}
                    disabled={isDestructive && deleteConfirmation !== "DELETE"}
                    className={`cursor-pointer rounded px-3 py-1 text-[9.5px] font-black tracking-wider uppercase transition disabled:cursor-not-allowed disabled:opacity-30 ${
                      isDestructive
                        ? "bg-red-500 text-white hover:bg-red-400"
                        : "bg-primary text-primary-foreground hover:bg-primary/95"
                    }`}
                  >
                    Approve
                  </button>
                </div>
              </div>
            </div>
          </motion.div>,
        );
        return nodes;
      }

      if (step.type === "ask_user_question") {
        nodes.push(
          <motion.div
            key={step.id || `ask-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className="border-primary/20 bg-primary/5 shadow-primary/5 mt-2 border p-3 shadow-lg select-none"
          >
            <div className="flex items-start gap-2">
              <HelpCircle size={14} className="text-primary mt-0.5" />
              <div className="flex-1 space-y-2">
                <p className="text-[10px] font-bold tracking-wider uppercase">
                  clarification required
                </p>
                {(
                  ((step.data ?? {}) as { questions?: ClarificationQuestion[] }).questions ?? []
                ).map((q: ClarificationQuestion, qIdx: number) => (
                  <div key={qIdx} className="space-y-1.5">
                    <p className="text-foreground/80 text-[10.5px] font-medium">{q.question}</p>
                    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                      {(q.options ?? []).map((opt, oIdx) => (
                        <button
                          key={oIdx}
                          onClick={() => {
                            const responseText = [opt.label, opt.description]
                              .filter(Boolean)
                              .join(" - ");
                            if (onClarifyAnswer) {
                              onClarifyAnswer(responseText);
                              return;
                            }
                            handleDecision(String(step.step_id), String(step.tool_id), true);
                          }}
                          className="hover:bg-primary/10 hover:border-primary/25 group cursor-pointer rounded border border-white/5 bg-white/5 p-1.5 text-left transition-all"
                        >
                          <div className="text-foreground/70 group-hover:text-primary text-[9.5px] font-bold transition-colors">
                            {opt.label}
                          </div>
                          {opt.description && (
                            <div className="text-foreground/35 mt-0.5 text-[8.5px]">
                              {opt.description}
                            </div>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>,
        );
        return nodes;
      }

      if (step.toolName) {
        nodes.push(
          <motion.div
            key={step.id || `tool-${idx}`}
            variants={stepVariants}
            initial="initial"
            animate="animate"
            layout="position"
            className="group space-y-1"
          >
            <div
              onClick={() => toggleExpand(step.id)}
              className={`-ml-2 flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1 transition-all duration-300 ${
                isRunning
                  ? "bg-primary/10 ring-primary/20 shadow-[0_0_15px_-3px_rgba(var(--primary),0.2)] ring-1"
                  : "text-foreground/80 hover:text-foreground hover:bg-white/5"
              }`}
            >
              <span className="text-foreground/30 group-hover:text-primary/50 shrink-0 text-[9px] font-bold transition-colors">
                {isExpanded ? "[-]" : "[+]"}
              </span>
              {getStepActivityRow(step)}
              {isRunning && (
                <div className="ml-1.5 flex shrink-0 items-center gap-1">
                  <motion.span
                    animate={{ scale: [1, 1.4, 1], opacity: [1, 0.4, 1] }}
                    transition={{ repeat: Infinity, duration: 1, ease: "easeInOut" }}
                    className="bg-primary h-1.5 w-1.5 rounded-full shadow-[0_0_8px_rgba(var(--primary),0.8)]"
                  />
                  <span className="text-primary animate-pulse text-[10px] font-bold">
                    {spinner}
                  </span>
                </div>
              )}
              {step.durationMs !== undefined && step.durationMs > 0 && (
                <span className="text-foreground/20 ml-auto shrink-0 font-mono text-[9px]">
                  {step.durationMs}ms
                </span>
              )}
            </div>
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0, scale: 0.98 }}
                  animate={{ height: "auto", opacity: 1, scale: 1 }}
                  exit={{ height: 0, opacity: 0, scale: 0.98 }}
                  transition={{ type: "spring", damping: 25, stiffness: 200 }}
                  className="mt-1 space-y-2 overflow-hidden border-l border-white/10 pl-4 text-[10px]"
                >
                  {step.toolInput && Object.keys(step.toolInput).length > 0 && (
                    <div className="mt-1">
                      <span className="text-foreground/35 text-[9px] tracking-tighter uppercase">
                        arguments:
                      </span>
                      {step.toolName === "todo_write" ? (
                        <div className="mt-1">
                          {renderStructuredToolInput(step.toolName, step.toolInput)}
                        </div>
                      ) : (
                        <pre className="text-primary/75 custom-scrollbar mt-1 max-h-40 overflow-x-auto rounded-md border border-white/5 bg-black/40 p-2 font-mono leading-relaxed shadow-inner backdrop-blur-sm">
                          {JSON.stringify(step.toolInput, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                  {step.toolOutput && (
                    <div className="pb-1">
                      <span className="text-foreground/35 text-[9px] tracking-tighter uppercase">
                        output:
                      </span>
                      <div className="relative mt-1">
                        {step.toolName === "todo_write" ? (
                          <div className="text-foreground/50 custom-scrollbar max-h-48 overflow-x-auto overflow-y-auto rounded-md border border-white/5 bg-black/40 p-2 leading-relaxed shadow-inner backdrop-blur-sm">
                            {renderStructuredToolOutput(step.toolName, step.toolOutput)}
                          </div>
                        ) : (
                          <pre className="text-foreground/50 custom-scrollbar max-h-48 overflow-x-auto overflow-y-auto rounded-md border border-white/5 bg-black/40 p-2 font-mono leading-relaxed whitespace-pre-wrap shadow-inner backdrop-blur-sm">
                            {step.toolOutput}
                          </pre>
                        )}
                        {isRunning && (
                          <motion.div
                            animate={{ opacity: [0, 0.1, 0], y: ["0%", "100%"] }}
                            transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
                            className="via-primary pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent to-transparent"
                          />
                        )}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>,
        );
        return nodes;
      }

      return nodes;
    });
  }, [flatSteps, expandedSteps, isStreaming, deleteConfirmation]);

  const statusText = useMemo(() => {
    if (!isActive) {
      const hasError = flatSteps.some((s) => s.type === "tool_error" || s.status === "failed");
      return hasError ? "Execution Failed" : "Execution Trace";
    }
    if (flatSteps.length === 0) return "Agent Active...";
    const latest = flatSteps[flatSteps.length - 1];
    if (latest.type === "permission_request" || latest.status === "awaiting_approval") {
      return "Clearance Required";
    }
    if (latest.toolName) {
      const toolLabel = TOOL_LABELS[latest.toolName] || latest.toolName;
      return `${toolLabel}...`;
    }
    if (latest.type === "observing" && latest.id === "synthetic-initial") {
      return "Agent Active...";
    }
    return "Agent Active...";
  }, [isActive, flatSteps]);

  const headerIcon = useMemo(() => {
    if (!isActive) {
      const hasError = flatSteps.some((s) => s.type === "tool_error" || s.status === "failed");
      return hasError ? "✘" : "✔";
    }
    if (flatSteps.length > 0) {
      const latest = flatSteps[flatSteps.length - 1];
      if (latest.type === "permission_request" || latest.status === "awaiting_approval") {
        return "⚠";
      }
    }
    return spinner;
  }, [isActive, flatSteps, spinner]);

  const handleDecision = (stepId: string, toolId: string, approved: boolean) => {
    onResume?.(stepId, toolId, approved);
  };

  const toggleExpand = (id: string) => {
    setExpandedSteps((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  return (
    <div className="flex flex-col gap-3">
      {(() => {
        const activeTimeline: TimelineStep[] =
          timeline && timeline.length > 0
            ? timeline
            : (steps ?? []).map((step) => ({
                id: step.id,
                stepId: step.stepId ?? step.id,
                turnIndex: step.turnIndex ?? 0,
                phase:
                  typeof step.data?.phase === "string"
                    ? (step.data.phase as TimelineStep["phase"])
                    : "exploring",
                type:
                  step.type === "plan"
                    ? "plan"
                    : step.type === "thinking"
                      ? "thinking"
                      : step.type === "permission_request" || step.type === "ask_user_question"
                        ? "permission"
                        : step.type === "agent_testing" ||
                            step.type === "agent_verifying" ||
                            step.type === "agent_self_correct"
                          ? "testing"
                          : ("tool_call" as const),
                title: (() => {
                  if (step.type === "plan") {
                    return (step.data?.title || step.data?.message || "Strategic Plan") as string;
                  }
                  if (step.type === "thinking") {
                    return "Internal Thought";
                  }
                  if (step.type === "permission_request") {
                    return "Clearance Required";
                  }
                  if (step.type === "ask_user_question") {
                    return "Clarification Needed";
                  }
                  if (step.type === "agent_testing") {
                    return "Testing Changes";
                  }
                  if (step.type === "agent_verifying") {
                    return "Verifying Fix";
                  }
                  if (step.type === "agent_self_correct") {
                    return "Self-Correcting";
                  }
                  if (step.type === "tool_error") {
                    return "Execution Error";
                  }
                  const toolName = step.toolName;
                  if (toolName) {
                    return (TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " ")) as string;
                  }
                  return "Executing Tool";
                })(),
                status: step.status,
                startedAt: step.startedAt,
                completedAt: step.completedAt,
                durationMs: step.durationMs,
                toolName: step.toolName,
                toolInput: step.toolInput,
                toolOutput: step.toolOutput,
                toolId: step.tool_id,
                success: step.success,
                diffStats: step.diffStats,
                details: step.plan,
                data: step.data,
              }));

        if (activeTimeline.length > 0 || (isStreaming && !hasContent)) {
          return (
            <AgentTimeline
              timeline={activeTimeline}
              isStreaming={isStreaming}
              onResume={onResume}
              onClarifyAnswer={onClarifyAnswer}
              hasContent={hasContent}
            />
          );
        }
        return null;
      })()}

      {/* Code Changes Consolidated Review Bar */}
      {modifiedFiles.length > 0 && (
        <div className="mt-2 flex items-center justify-between rounded border-t border-white/5 bg-white/[0.01] px-2 py-1.5">
          <div className="flex items-center gap-2 text-[9.5px] font-bold select-none">
            <span className="text-foreground/35 tracking-wide uppercase">Code changes:</span>
            <span className="text-foreground/70 font-mono">
              {modifiedFiles.length} file{modifiedFiles.length !== 1 ? "s" : ""} modified
            </span>
            <span className="text-foreground/30 font-mono">
              (<span className="text-emerald-400">+{totalAdditions}</span>{" "}
              <span className="text-red-400">-{totalDeletions}</span>)
            </span>
          </div>
          <button
            type="button"
            onClick={() => setIsReviewOpen(true)}
            className="bg-primary/10 border-primary/25 text-primary hover:bg-primary/20 flex cursor-pointer items-center gap-1 rounded border px-2 py-1 text-[9px] font-black tracking-wider uppercase transition-colors"
          >
            <Code size={11} />
            <span>Review Changes</span>
          </button>
        </div>
      )}

      {/* Diff Review Modal */}
      <AnimatePresence>
        {isReviewOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm select-none">
            <div className="relative flex h-[75vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-white/10 bg-[#070707] font-mono shadow-2xl">
              {/* Modal Header */}
              <div className="flex items-center justify-between border-b border-white/10 bg-black/30 px-4 py-2.5">
                <div>
                  <h3 className="text-primary text-[10px] font-bold tracking-widest uppercase">
                    WORKSPACE activity diff review
                  </h3>
                  <p className="text-foreground/45 mt-0.5 text-[8.5px]">
                    {modifiedFiles.length} file{modifiedFiles.length !== 1 ? "s" : ""} modified •{" "}
                    <span className="font-mono text-emerald-400">+{totalAdditions}</span> additions
                    • <span className="font-mono text-red-400">-{totalDeletions}</span> deletions
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsReviewOpen(false)}
                  className="text-foreground/40 hover:text-foreground/80 cursor-pointer rounded border border-white/5 bg-white/5 p-1 transition hover:bg-white/10"
                >
                  <X size={13} />
                </button>
              </div>

              {/* Modal Body */}
              <div className="flex flex-1 overflow-hidden select-none">
                {/* Sidebar */}
                <div className="flex w-56 flex-shrink-0 flex-col space-y-1 overflow-y-auto border-r border-white/5 bg-[#050505] p-2 select-none">
                  <span className="text-foreground/20 mb-1.5 pl-1.5 text-[8px] font-bold tracking-wider uppercase">
                    files list
                  </span>
                  {modifiedFiles.map((file) => {
                    const isSelected = selectedReviewFile === file.path;
                    const filename = file.path.split("/").pop() || file.path;
                    return (
                      <button
                        key={file.path}
                        type="button"
                        onClick={() => setSelectedReviewFile(file.path)}
                        className={`flex w-full cursor-pointer items-center justify-between rounded border px-2 py-1.5 text-left transition-all ${
                          isSelected
                            ? "bg-primary/10 border-primary/20 text-foreground"
                            : "text-foreground/40 hover:text-foreground/70 border-transparent bg-transparent hover:bg-white/[0.01]"
                        }`}
                      >
                        <span className="max-w-[120px] truncate text-[10px] font-bold">
                          {filename}
                        </span>
                        <span className="shrink-0 text-[8px] font-bold">
                          <span className="text-emerald-400">+{file.additions}</span>
                          <span className="ml-1 text-red-400">-{file.deletions}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>

                {/* Diff Area */}
                <div className="flex flex-1 flex-col overflow-auto bg-black/55 select-text">
                  {selectedReviewFile ? (
                    <>
                      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/5 bg-[#070707]/90 px-4 py-1.5 backdrop-blur-md select-none">
                        <span className="text-foreground/50 max-w-md truncate text-[9.5px] select-all">
                          {selectedReviewFile}
                        </span>
                        {(() => {
                          const file = modifiedFiles.find((f) => f.path === selectedReviewFile);
                          if (!file) return null;
                          return (
                            <span className="text-[9px] font-bold">
                              <span className="text-emerald-400">+{file.additions}</span>{" "}
                              <span className="text-red-400">-{file.deletions}</span>
                            </span>
                          );
                        })()}
                      </div>
                      <div className="flex-1 p-3 select-text">
                        <div className="overflow-hidden rounded border border-white/5 bg-[#020202] select-text">
                          {(() => {
                            const file = modifiedFiles.find((f) => f.path === selectedReviewFile);
                            if (!file || !file.diffLines || file.diffLines.length === 0) {
                              return (
                                <div className="text-foreground/25 flex flex-col items-center justify-center py-12 text-[10px]">
                                  No diff lines generated.
                                </div>
                              );
                            }

                            let oldNum = 1;
                            let newNum = 1;
                            const linesToRender = file.diffLines.map((line) => {
                              const type = line.type;
                              let leftNum: string | number = "";
                              let rightNum: string | number = "";
                              if (type === "added") {
                                rightNum = newNum++;
                              } else if (type === "removed") {
                                leftNum = oldNum++;
                              } else {
                                leftNum = oldNum++;
                                rightNum = newNum++;
                              }
                              return {
                                type,
                                leftNum,
                                rightNum,
                                text: line.text,
                              };
                            });

                            return (
                              <div className="divide-y divide-white/[0.03] py-1.5 text-[10.5px] leading-relaxed select-text">
                                {linesToRender.map((line, idx) => {
                                  let bgClass = "hover:bg-white/[0.01]";
                                  let textClass = "text-foreground/75";
                                  let indicator = " ";
                                  let indicatorClass = "text-foreground/15";
                                  if (line.type === "added") {
                                    bgClass = "bg-emerald-500/5 hover:bg-emerald-500/8";
                                    textClass = "text-emerald-300";
                                    indicator = "+";
                                    indicatorClass = "text-emerald-400 font-bold";
                                  } else if (line.type === "removed") {
                                    bgClass = "bg-red-500/5 hover:bg-red-500/8";
                                    textClass =
                                      "text-red-300/80 line-through decoration-red-950/40";
                                    indicator = "-";
                                    indicatorClass = "text-red-400 font-bold";
                                  }

                                  return (
                                    <div
                                      key={idx}
                                      className={`flex min-w-full items-stretch ${bgClass} select-text`}
                                    >
                                      <div className="text-foreground/15 w-10 border-r border-white/5 py-0.5 pr-2 text-right text-[9px] select-none">
                                        {line.leftNum}
                                      </div>
                                      <div className="text-foreground/15 w-10 border-r border-white/5 py-0.5 pr-2 text-right text-[9px] select-none">
                                        {line.rightNum}
                                      </div>
                                      <div
                                        className={`flex w-5 items-center justify-center border-r border-white/5 text-[9px] select-none ${indicatorClass}`}
                                      >
                                        {indicator}
                                      </div>
                                      <div
                                        className={`flex-1 py-0.5 pl-3 break-all whitespace-pre-wrap ${textClass} select-text`}
                                      >
                                        {line.text}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-foreground/25 flex h-full flex-col items-center justify-center text-[10px]">
                      Select a file from the sidebar to review changes
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
