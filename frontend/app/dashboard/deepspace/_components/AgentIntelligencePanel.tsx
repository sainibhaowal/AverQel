"use client";

import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  Cpu,
  Database,
  RefreshCw,
  ShieldCheck,
  GitBranch,
  Loader2,
  X,
  CheckSquare,
  Check,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchWithAuth } from "@/lib/api";
import type { AgentStep, ConversationCompactionState } from "../_lib/deepspace-stream";

interface IntelligenceProps {
  contextUsage: number; // 0 to 1
  tokenCount: number;
  activeTools: string[];
  contextLimit: number | null;
  contextLimitSource?: string | null;
  contextUsedTokens: number;
  contextRemainingTokens: number | null;
  modelName?: string | null;
  providerType?: string | null;
  phase?: string | null;
  compaction?: ConversationCompactionState | null;
  latencyTimeline?: Array<{
    label: string;
    atMs: number;
    detail?: string;
  }>;
  agentSteps?: AgentStep[];
  vitals?: {
    internet: string;
    llm: string;
    web_search: string;
    sources: number;
    proactive_daemon?: {
      enabled: boolean;
      phase: string;
      timestamp?: string | null;
      interval_seconds?: number | null;
      healthy: boolean;
    } | null;
  } | null;
  onCompactNow: () => void;
  variant?: "sidebar" | "drawer";
}

interface SubagentRun {
  run_id: string;
  subagent_type: string;
  prompt: string;
  status: string;
  slot_index: number;
  summary?: string;
  final_output?: string;
  error?: string;
  last_event_type?: string;
  last_event_message?: string;
  step_count?: number;
  duration_ms?: number;
  created_at?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  heartbeat_at?: string | null;
  cancel_requested?: boolean;
}

function formatStatus(value?: string): string {
  if (!value) return "unknown";
  return value.replace(/_/g, " ");
}

function formatSource(value?: string | null): string | null {
  if (!value) return null;
  return value.replace(/_/g, " ").replace(/:/g, " · ");
}

function formatRunStatus(value?: string | null): string {
  if (!value) return "unknown";
  return value.replace(/_/g, " ");
}

function formatPhase(value?: string | null): string {
  if (!value) return "idle";
  return value.replace(/_/g, " ");
}

export default function AgentIntelligencePanel({
  contextUsage = 0.45,
  tokenCount = 12450,
  activeTools = [],
  contextLimit = null,
  contextLimitSource = null,
  contextUsedTokens = tokenCount,
  contextRemainingTokens = null,
  modelName,
  providerType,
  phase,
  compaction,
  latencyTimeline = [],
  agentSteps = [],
  vitals,
  onCompactNow,
  variant = "sidebar",
}: IntelligenceProps) {
  const effectiveUsage =
    typeof contextLimit === "number" && contextLimit > 0
      ? Math.min(1, contextUsedTokens / contextLimit)
      : contextUsage;
  const isNearLimit = effectiveUsage >= 0.8;
  const isCritical = effectiveUsage >= 0.95;
  const vitalsOptimal =
    vitals?.internet === "connected" &&
    vitals?.llm === "connected" &&
    vitals?.web_search === "available";
  const daemonHealthy = Boolean(vitals?.proactive_daemon?.healthy);
  const [subagentRuns, setSubagentRuns] = useState<SubagentRun[]>([]);
  const [subagentsLoading, setSubagentsLoading] = useState(false);
  const [subagentsError, setSubagentsError] = useState<string | null>(null);

  const loadSubagentRuns = useCallback(async () => {
    setSubagentsLoading(true);
    setSubagentsError(null);
    try {
      const response = (await fetchWithAuth("/deepspace/chats/subagents?limit=8")) as Response;
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = (await response.json()) as SubagentRun[];
      setSubagentRuns(Array.isArray(payload) ? payload : []);
    } catch (error) {
      setSubagentsError(error instanceof Error ? error.message : "Failed to load sub-agents");
    } finally {
      setSubagentsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSubagentRuns();
    const timer = window.setInterval(() => {
      void loadSubagentRuns();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [loadSubagentRuns]);

  const activeSubagents = useMemo(
    () => subagentRuns.filter((run) => run.status === "running"),
    [subagentRuns],
  );

  const handleTerminateSubagent = useCallback(
    async (runId: string) => {
      try {
        const response = (await fetchWithAuth(`/deepspace/chats/subagents/${runId}/terminate`, {
          method: "POST",
        })) as Response;
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        await loadSubagentRuns();
      } catch (error) {
        setSubagentsError(error instanceof Error ? error.message : "Failed to terminate sub-agent");
      }
    },
    [loadSubagentRuns],
  );

  return (
    <div
      className={
        variant === "drawer"
          ? "backdrop-blur-0 flex h-full flex-col bg-transparent"
          : "bg-background/40 flex h-full flex-col border-l border-white/5 backdrop-blur-3xl"
      }
    >
      <div className="custom-scrollbar min-h-0 flex-1 space-y-8 overflow-y-auto p-6">
        {/* Context Meter */}
        <section>
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Cpu size={16} className="text-primary" />
              <h3 className="text-foreground/70 text-[11px] font-black tracking-[0.2em] uppercase">
                Context Meter
              </h3>
            </div>
            <span className="text-foreground/40 font-mono text-[10px]">
              {contextUsedTokens.toLocaleString()} /
              {typeof contextLimit === "number" && contextLimit > 0
                ? `${contextLimit.toLocaleString()} tokens`
                : "unknown"}
            </span>
          </div>

          <div className="relative h-2 w-full overflow-hidden rounded-full border border-white/5 bg-white/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${effectiveUsage * 100}%` }}
              className={`h-full transition-colors duration-500 ${
                isCritical
                  ? "bg-red-500 shadow-[0_0_15px_rgba(239,68,68,0.5)]"
                  : isNearLimit
                    ? "bg-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.5)]"
                    : "bg-primary shadow-[0_0_15px_rgba(var(--primary),0.5)]"
              }`}
            />
          </div>

          <div className="mt-3 flex items-center justify-between gap-3">
            <p
              className={`text-[10px] font-bold ${
                isNearLimit ? "text-amber-400" : "text-foreground/40"
              }`}
            >
              {Math.round(effectiveUsage * 100)}% Used
            </p>
            {isNearLimit && (
              <motion.div
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 2, repeat: Infinity }}
                className="flex items-center gap-1.5 text-[9px] font-black tracking-tighter text-amber-500 uppercase"
              >
                <AlertTriangle size={10} /> Will Compact Soon
              </motion.div>
            )}
          </div>

          {compaction ? (
            <div className="mt-4 rounded-xl border border-emerald-500/15 bg-emerald-500/5 p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-black tracking-[0.18em] text-emerald-300 uppercase">
                  Last Compaction
                </p>
                <span className="font-mono text-[9px] text-emerald-200/80">
                  {compaction.trigger.replace(/_/g, " ")}
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-5 text-emerald-100/85">
                Saved {compaction.savedTokens.toLocaleString()} tokens and summarized{" "}
                {compaction.summarizedCount} older messages.
              </p>
              <p className="mt-2 font-mono text-[9px] text-emerald-100/55">
                {compaction.afterTokens.toLocaleString()} tokens kept after compacting.
              </p>
            </div>
          ) : null}

          <button
            onClick={onCompactNow}
            className="text-foreground/40 hover:text-primary group mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-white/5 bg-white/5 py-2 text-[10px] font-black tracking-widest uppercase transition-all hover:bg-white/10"
          >
            <RefreshCw
              size={12}
              className="transition-transform duration-500 group-hover:rotate-180"
            />
            Compact Now
          </button>
        </section>

        {/* Mission Checklist */}
        {(() => {
          const lastTodoWrite = [...agentSteps].reverse().find((s) => s.toolName === "todo_write");
          if (!lastTodoWrite || !lastTodoWrite.toolInput) return null;
          const todoList =
            (lastTodoWrite.toolInput as { todos?: Array<{ content: string; status: string }> })
              .todos ?? [];
          if (todoList.length === 0) return null;

          return (
            <section className="bg-primary/5 border-primary/10 shadow-primary/5 rounded-xl border p-4 shadow-inner">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <CheckSquare size={16} className="text-primary" />
                  <h3 className="text-primary/70 text-[11px] font-black tracking-[0.2em] uppercase">
                    Mission Objectives
                  </h3>
                </div>
                <span className="text-primary/40 font-mono text-[9px]">
                  {todoList.filter((t) => t.status === "completed").length} / {todoList.length}
                </span>
              </div>
              <div className="space-y-3">
                {todoList.map((todo, idx) => (
                  <div key={idx} className="group flex items-start gap-3">
                    <div
                      className={`mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-all duration-300 ${
                        todo.status === "completed"
                          ? "bg-primary border-primary text-primary-foreground"
                          : todo.status === "in_progress"
                            ? "border-primary/50 bg-primary/10"
                            : "border-white/10 bg-white/5"
                      }`}
                    >
                      {todo.status === "completed" && <Check size={10} strokeWidth={4} />}
                      {todo.status === "in_progress" && (
                        <motion.div
                          animate={{ scale: [1, 1.3, 1], opacity: [1, 0.5, 1] }}
                          transition={{ repeat: Infinity, duration: 2 }}
                          className="bg-primary h-1.5 w-1.5 rounded-full shadow-[0_0_8px_rgba(var(--primary),0.8)]"
                        />
                      )}
                    </div>
                    <span
                      className={`text-[11px] leading-tight transition-all duration-300 ${
                        todo.status === "completed"
                          ? "text-foreground/30 line-through"
                          : "text-foreground/80"
                      }`}
                    >
                      {todo.content}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          );
        })()}

        {/* Active Tools */}
        <section>
          <div className="mb-4 flex items-center gap-2">
            <Activity size={16} className="text-emerald-400" />
            <h3 className="text-foreground/70 text-[11px] font-black tracking-[0.2em] uppercase">
              Live Tools
            </h3>
          </div>
          <div className="space-y-2">
            {activeTools.length === 0 ? (
              <p className="text-foreground/20 text-[10px] italic">No active operations.</p>
            ) : (
              activeTools.map((tool, idx) => (
                <motion.div
                  key={`${tool}-${idx}`}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-center justify-between rounded-lg border border-white/5 bg-white/5 p-2.5"
                >
                  <span className="text-foreground/60 font-mono text-[10px]">{tool}</span>
                  <div className="flex gap-1">
                    <span className="h-1 w-1 animate-pulse rounded-full bg-emerald-400" />
                  </div>
                </motion.div>
              ))
            )}
          </div>
        </section>

        {/* Sub-agent Monitor */}
        <section>
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <GitBranch size={16} className="text-cyan-400" />
              <h3 className="text-foreground/70 text-[11px] font-black tracking-[0.2em] uppercase">
                Sub-agent Monitor
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full border border-cyan-500/20 bg-cyan-500/5 px-2 py-0.5 text-[9px] font-black tracking-widest text-cyan-300 uppercase">
                {activeSubagents.length} running
              </span>
              <button
                type="button"
                onClick={() => void loadSubagentRuns()}
                className="text-foreground/35 hover:text-primary rounded-full border border-white/5 bg-white/5 p-1.5 transition hover:bg-white/10"
                aria-label="Refresh sub-agent runs"
                title="Refresh"
              >
                <RefreshCw size={12} className={subagentsLoading ? "animate-spin" : ""} />
              </button>
            </div>
          </div>

          {subagentsError ? (
            <div className="mb-2 rounded-lg border border-red-500/20 bg-red-500/5 p-2 text-[10px] text-red-300/80">
              {subagentsError}
            </div>
          ) : null}

          <div className="space-y-2">
            {subagentsLoading && subagentRuns.length === 0 ? (
              <div className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/5 p-3 text-[10px] text-white/35">
                <Loader2 size={12} className="animate-spin text-cyan-300/70" />
                Loading sub-agent runs...
              </div>
            ) : subagentRuns.length === 0 ? (
              <p className="text-foreground/20 text-[10px] italic">
                No sub-agent runs yet. Spawn one from AverQel to monitor it here.
              </p>
            ) : (
              subagentRuns.map((run) => (
                <motion.div
                  key={run.run_id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-white/5 bg-white/5 p-3"
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-foreground/85 text-[11px] font-black tracking-tight">
                          {run.subagent_type}
                        </span>
                        <span className="rounded-full border border-white/10 bg-black/30 px-2 py-0.5 text-[9px] font-bold tracking-widest text-white/35 uppercase">
                          {formatRunStatus(run.status)}
                        </span>
                      </div>
                      <p className="text-foreground/35 mt-1 line-clamp-2 text-[10px] leading-relaxed">
                        {run.prompt}
                      </p>
                    </div>
                    {run.status === "running" ? (
                      <button
                        type="button"
                        onClick={() => void handleTerminateSubagent(run.run_id)}
                        className="inline-flex items-center gap-1 rounded-full border border-red-500/20 bg-red-500/10 px-2.5 py-1 text-[9px] font-black tracking-widest text-red-300 uppercase transition hover:bg-red-500/20"
                      >
                        <X size={10} />
                        Terminate
                      </button>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap gap-2 text-[9px] font-bold tracking-[0.16em] text-white/35 uppercase">
                    <span>Events: {run.step_count ?? 0}</span>
                    <span>Lane: {run.slot_index}</span>
                    <span>Updated: {run.heartbeat_at ?? run.updated_at ?? "now"}</span>
                  </div>

                  {run.summary ? (
                    <p className="text-foreground/55 mt-2 line-clamp-3 text-[10px] leading-relaxed">
                      {run.summary}
                    </p>
                  ) : run.last_event_message ? (
                    <p className="text-foreground/45 mt-2 line-clamp-3 text-[10px] leading-relaxed">
                      {run.last_event_message}
                    </p>
                  ) : null}

                  {run.error ? (
                    <div className="mt-2 rounded-lg border border-red-500/20 bg-red-500/5 p-2 text-[10px] text-red-200/80">
                      {run.error}
                    </div>
                  ) : null}
                </motion.div>
              ))
            )}
          </div>
        </section>

        {/* Runtime Snapshot */}
        <section>
          <div className="mb-4 flex items-center gap-2">
            <Database size={16} className="text-purple-400" />
            <h3 className="text-foreground/70 text-[11px] font-black tracking-[0.2em] uppercase">
              Runtime Snapshot
            </h3>
          </div>
          <div className="bg-primary/5 border-primary/10 space-y-3 rounded-xl border p-4">
            <div className="flex items-center justify-between gap-4">
              <span className="text-foreground/40 text-[9px] font-black tracking-[0.22em] uppercase">
                Model
              </span>
              <span className="text-foreground/80 max-w-[12rem] truncate font-mono text-[10px]">
                {modelName ?? "Auto-selected"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-foreground/40 text-[9px] font-black tracking-[0.22em] uppercase">
                Provider
              </span>
              <span className="text-foreground/80 font-mono text-[10px]">
                {providerType ?? "chat"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-foreground/40 text-[9px] font-black tracking-[0.22em] uppercase">
                Limit
              </span>
              <div className="flex flex-col items-end gap-1">
                <span className="text-foreground/80 font-mono text-[10px]">
                  {typeof contextLimit === "number" && contextLimit > 0
                    ? `${contextLimit.toLocaleString()} tokens`
                    : "unknown"}
                </span>
                {contextLimitSource ? (
                  <span className="text-foreground/35 font-mono text-[8px] tracking-[0.14em] uppercase">
                    {formatSource(contextLimitSource)}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-foreground/40 text-[9px] font-black tracking-[0.22em] uppercase">
                Remaining
              </span>
              <span className="text-foreground/80 font-mono text-[10px]">
                {typeof contextRemainingTokens === "number"
                  ? `${contextRemainingTokens.toLocaleString()} tokens`
                  : "unknown"}
              </span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span className="text-foreground/40 text-[9px] font-black tracking-[0.22em] uppercase">
                Phase
              </span>
              <span className="text-foreground/80 font-mono text-[10px] uppercase">
                {formatPhase(phase)}
              </span>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-4 flex items-center gap-2">
            <RefreshCw size={16} className="text-amber-400" />
            <h3 className="text-foreground/70 text-[11px] font-black tracking-[0.2em] uppercase">
              Live Timeline
            </h3>
          </div>
          <div className="space-y-2">
            {latencyTimeline.length === 0 ? (
              <p className="text-foreground/20 text-[10px] italic">
                Waiting for live execution milestones.
              </p>
            ) : (
              latencyTimeline.slice(-6).map((item, index) => (
                <motion.div
                  key={`${item.label}-${item.atMs}-${index}`}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-lg border border-white/5 bg-white/5 p-2.5"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-foreground/70 text-[10px] font-black uppercase">
                      {formatPhase(item.label)}
                    </span>
                    <span className="text-foreground/35 font-mono text-[10px]">{item.atMs}ms</span>
                  </div>
                  {item.detail ? (
                    <p className="text-foreground/35 mt-1 line-clamp-2 text-[9px] leading-relaxed">
                      {item.detail}
                    </p>
                  ) : null}
                </motion.div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* Footer Info */}
      <div className="group shrink-0 border-t border-white/5 p-6 transition-opacity hover:opacity-100">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck size={13} className="text-emerald-400" />
            <p className="text-[10px] font-black tracking-[0.24em] text-emerald-300 uppercase">
              Vitals: {vitalsOptimal ? "OPTIMAL" : "DEGRADED"}
            </p>
          </div>
          <p className="text-foreground/40 text-[9px] font-medium tracking-[0.12em] italic">
            Context Auto-Compaction: Enabled
          </p>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[9px] font-bold tracking-[0.18em] text-white/35 uppercase">
          <span>Internet: {formatStatus(vitals?.internet)}</span>
          <span>LLM: {formatStatus(vitals?.llm)}</span>
          <span>Web Search: {formatStatus(vitals?.web_search)}</span>
          <span>Sources: {vitals?.sources ?? 0}</span>
          <span>
            Daemon:{" "}
            {vitals?.proactive_daemon?.enabled
              ? `${formatStatus(vitals?.proactive_daemon?.phase)}${daemonHealthy ? "" : " (stale)"}`
              : "disabled"}
          </span>
        </div>
      </div>
    </div>
  );
}
