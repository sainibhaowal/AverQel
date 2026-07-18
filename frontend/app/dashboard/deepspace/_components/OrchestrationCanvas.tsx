"use client";

import {
  Activity,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock3,
  GitBranch,
  Layers3,
  Radar,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
} from "lucide-react";

import type {
  MissionCanvasState,
  DurableMissionRuntimeState,
  MissionLaneStatus,
  MissionLaneVisual,
} from "../_lib/deepspace-stream";
import RuntimeIndicatorChips, { type RuntimeIndicatorState } from "./RuntimeIndicatorChips";

const STATUS_STYLES: Record<MissionLaneStatus | MissionCanvasState["status"], string> = {
  planned: "border-white/10 bg-white/5 text-white/60",
  running: "border-cyan-400/20 bg-cyan-400/10 text-cyan-200",
  awaiting_approval: "border-amber-400/25 bg-amber-400/10 text-amber-200",
  completed: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
  failed: "border-red-400/25 bg-red-400/10 text-red-200",
  cancelled: "border-zinc-400/25 bg-zinc-400/10 text-zinc-200",
  blocked: "border-orange-400/25 bg-orange-400/10 text-orange-200",
  planning: "border-fuchsia-400/25 bg-fuchsia-400/10 text-fuchsia-200",
};

const LAYER_ORDER = [
  "Mission Control",
  "Support + Proactive",
  "Discovery + Analysis",
  "Delivery + Execution",
  "Additional Lanes",
] as const;

function classifyLaneLayer(lane: MissionLaneVisual): (typeof LAYER_ORDER)[number] {
  if (lane.laneType === "main_chat") {
    return "Mission Control";
  }
  if (lane.laneType === "support" || lane.metadata?.role === "support") {
    return "Support + Proactive";
  }
  if (
    lane.laneType === "research" ||
    lane.laneType === "analysis" ||
    lane.laneType === "planner" ||
    lane.laneType === "file"
  ) {
    return "Discovery + Analysis";
  }
  if (lane.laneType === "writer" || lane.laneType === "executor") {
    return "Delivery + Execution";
  }
  return "Additional Lanes";
}

function formatStatus(status: string): string {
  return status.replace(/_/g, " ");
}

function statusClass(status: string): string {
  return STATUS_STYLES[status as keyof typeof STATUS_STYLES] ?? STATUS_STYLES.planned;
}

function laneIcon(lane: MissionLaneVisual) {
  if (lane.laneType === "support" || lane.metadata?.role === "support") {
    return <Radar size={14} />;
  }
  if (lane.laneType === "writer" || lane.laneType === "executor") {
    return <TerminalSquare size={14} />;
  }
  if (lane.laneType === "research" || lane.laneType === "analysis") {
    return <Activity size={14} />;
  }
  return <Bot size={14} />;
}

function formatRuntimeProfile(value: string | undefined): string {
  if (!value || value === "default") {
    return "Adaptive";
  }
  return value.replace(/_/g, " ");
}

function formatCompactLabel(value: string | undefined): string {
  return (value || "").replace(/_/g, " ").trim();
}

function DurableRuntimeStrip({ runtime }: { runtime: DurableMissionRuntimeState }) {
  const budgetEntries = Object.entries(runtime.budgetUsage ?? {}).slice(0, 4);
  return (
    <div className="mt-3 rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.05] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-black tracking-[0.18em] text-cyan-100/75 uppercase">
        <span>Native Durable Runtime</span>
        <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2 py-1 text-cyan-100">
          {runtime.reconnectState}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-white/55 sm:grid-cols-6">
        <span>Run <b className="font-mono text-white/80">{runtime.runId.slice(0, 8)}</b></span>
        <span>Status <b className="text-white/80">{runtime.status ?? "—"}</b></span>
        <span>Cursor <b className="font-mono text-white/80">#{runtime.lastSequence}</b></span>
        <span>Checkpoint <b className="font-mono text-white/80">#{runtime.checkpointSequence ?? "—"}</b></span>
        <span>Epoch <b className="font-mono text-white/80">{runtime.continuationEpoch ?? 0}</b></span>
        <span>Recovery <b className="font-mono text-white/80">{runtime.recoveryCount ?? 0}</b></span>
      </div>
      {budgetEntries.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-cyan-100/60">
          {budgetEntries.map(([key, value]) => (
            <span key={key} className="rounded-full border border-white/10 bg-black/15 px-2 py-1">
              {key.replace(/_/g, " ")}: {String(value)}
              {runtime.budgetLimits?.[key] !== undefined ? ` / ${runtime.budgetLimits[key]}` : ""}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-white/45">
        <span>Supervisor: {runtime.supervisorDecision ?? "observing"}</span>
        <span>Replay: read-only</span>
        {(runtime.pendingApprovals ?? 0) > 0 ? <span className="text-amber-200">Approvals: {runtime.pendingApprovals}</span> : null}
      </div>
    </div>
  );
}

export default function OrchestrationCanvas({
  mission,
  runtimeIndicators,
}: {
  mission: MissionCanvasState;
  runtimeIndicators?: RuntimeIndicatorState | null;
}) {
  const grouped = LAYER_ORDER.map((label) => ({
    label,
    lanes: mission.lanes.filter((lane) => classifyLaneLayer(lane) === label),
  })).filter((group) => group.lanes.length > 0);

  const activeCount = mission.lanes.filter((lane) => lane.status === "running").length;
  const completedCount = mission.lanes.filter((lane) => lane.status === "completed").length;
  const approvalCount = mission.lanes.filter((lane) => lane.status === "awaiting_approval").length;
  const failedCount = mission.lanes.filter((lane) => lane.status === "failed").length;
  const graphEdges = Array.isArray(mission.graph?.edges) ? (mission.graph?.edges ?? []) : [];
  const effectiveRuntimeIndicators = runtimeIndicators
    ? {
        ...runtimeIndicators,
        plannerMode:
          (mission.runtimeState?.plannerMode as RuntimeIndicatorState["plannerMode"] | undefined) ??
          runtimeIndicators.plannerMode,
        subagentProfile:
          (mission.runtimeState?.subagentProfile as
            | RuntimeIndicatorState["subagentProfile"]
            | undefined) ?? runtimeIndicators.subagentProfile,
        runtimeHooksEnabled:
          mission.runtimeState?.runtimeHooksState === "disabled"
            ? false
            : mission.runtimeState?.runtimeHooksState === "active"
              ? true
              : runtimeIndicators.runtimeHooksEnabled,
        workspaceModeEnabled:
          mission.runtimeState?.workspaceModeEnabled ?? runtimeIndicators.workspaceModeEnabled,
      }
    : null;
  const toolDensity = mission.runtimeState?.diagnostics?.toolDensity;
  const policyCounts = mission.runtimeState?.diagnostics?.policy?.counts;
  const recentPolicy = mission.runtimeState?.diagnostics?.policy?.recent?.slice(-3).reverse() ?? [];
  const recentHooks = mission.runtimeState?.diagnostics?.hooks?.recent?.slice(-3).reverse() ?? [];
  const recentCompaction =
    mission.runtimeState?.diagnostics?.compaction?.recent?.slice(-2).reverse() ?? [];
  const plannerDiagnostics = mission.runtimeState?.diagnostics?.planner;

  return (
    <section className="mb-6 overflow-hidden rounded-[28px] border border-cyan-400/15 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_35%),linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] shadow-[0_24px_80px_rgba(0,0,0,0.24)]">
      <div className="border-b border-white/8 px-5 py-4 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[10px] font-black tracking-[0.22em] text-cyan-100 uppercase">
                <Layers3 size={12} />
                Mission Canvas
              </span>
              <span
                className={`rounded-full border px-3 py-1 text-[10px] font-black tracking-[0.22em] uppercase ${statusClass(mission.status)}`}
              >
                {formatStatus(mission.status)}
              </span>
              <span className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-[10px] font-black tracking-[0.22em] text-white/55 uppercase">
                {mission.phase.replace(/_/g, " ")}
              </span>
            </div>

            <div>
              <h3 className="text-lg font-black tracking-tight text-white/95">
                {mission.objective || "Mission orchestration"}
              </h3>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-white/60">
                {mission.summary || "AverQel is planning and coordinating lane execution."}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[10px] font-bold tracking-[0.2em] text-white/55 uppercase sm:grid-cols-4">
            <MetricCard label="Active" value={String(activeCount)} tone="cyan" />
            <MetricCard label="Done" value={String(completedCount)} tone="emerald" />
            <MetricCard label="Approvals" value={String(approvalCount)} tone="amber" />
            <MetricCard label="Failed" value={String(failedCount)} tone="red" />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 text-[10px] font-bold tracking-[0.18em] text-white/45 uppercase">
          {mission.plannerSource ? (
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
              Planner: {mission.plannerSource}
            </span>
          ) : null}
          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
            Mission ID: {mission.missionId.slice(0, 8)}
          </span>
          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
            Updated: {new Date(mission.lastUpdatedAt).toLocaleTimeString()}
          </span>
        </div>

        {effectiveRuntimeIndicators ? (
          <div className="mt-3">
            <RuntimeIndicatorChips indicators={effectiveRuntimeIndicators} compact />
          </div>
        ) : mission.executionMode ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-bold tracking-[0.18em] text-white/60 uppercase">
              Mode: {mission.executionMode.replace(/_/g, " ")}
            </span>
          </div>
        ) : null}

        {mission.runtimeState ? (
          <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-bold tracking-[0.18em] text-white/45 uppercase">
            {mission.runtimeState.plannerValidationStatus ? (
              <span className="rounded-full border border-emerald-400/18 bg-emerald-400/10 px-2.5 py-1 text-emerald-100">
                Validation: {mission.runtimeState.plannerValidationStatus.replace(/_/g, " ")}
              </span>
            ) : null}
            {mission.runtimeState.runtimeHooksState ? (
              <span className="rounded-full border border-cyan-400/18 bg-cyan-400/10 px-2.5 py-1 text-cyan-100">
                Hooks: {mission.runtimeState.runtimeHooksState}
              </span>
            ) : null}
            {mission.runtimeState.subagentProfileClassification ? (
              <span className="rounded-full border border-amber-400/18 bg-amber-400/10 px-2.5 py-1 text-amber-100">
                Delegation: {mission.runtimeState.subagentProfileClassification.replace(/_/g, " ")}
              </span>
            ) : null}
          </div>
        ) : null}
        {mission.durableRuntime ? <DurableRuntimeStrip runtime={mission.durableRuntime} /> : null}
      </div>

      <div className="grid gap-5 px-5 py-5 sm:px-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-5">
          {mission.signals && Object.keys(mission.signals).length > 0 ? (
            <div className="rounded-2xl border border-white/8 bg-black/15 p-4">
              <div className="mb-3 flex items-center gap-2 text-[11px] font-black tracking-[0.24em] text-white/55 uppercase">
                <Sparkles size={12} className="text-cyan-300" />
                Mission Signals
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(mission.signals).map(([key, value]) => (
                  <span
                    key={key}
                    className={`rounded-full border px-2.5 py-1 text-[10px] font-bold tracking-[0.18em] uppercase ${
                      value
                        ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
                        : "border-white/10 bg-white/5 text-white/50"
                    }`}
                  >
                    {key.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <div className="space-y-4">
            {grouped.map((group) => (
              <div key={group.label} className="rounded-2xl border border-white/8 bg-black/15 p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cyan-300" />
                  <h4 className="text-[11px] font-black tracking-[0.24em] text-white/60 uppercase">
                    {group.label}
                  </h4>
                </div>
                <div className="grid gap-3 xl:grid-cols-2">
                  {group.lanes.map((lane) => (
                    <LaneCard key={lane.laneId} lane={lane} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-2xl border border-white/8 bg-black/15 p-4">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-black tracking-[0.24em] text-white/55 uppercase">
              <GitBranch size={12} className="text-cyan-300" />
              Dependency Map
            </div>
            {graphEdges.length > 0 ? (
              <div className="space-y-2">
                {graphEdges.map((edge, index) => (
                  <div
                    key={`${String(edge.from ?? "from")}-${String(edge.to ?? "to")}-${index}`}
                    className="flex items-center gap-2 rounded-xl border border-white/8 bg-white/5 px-3 py-2 text-xs text-white/65"
                  >
                    <span className="rounded-full border border-white/10 bg-black/20 px-2 py-1 font-mono text-[10px]">
                      {String(edge.from ?? "unknown")}
                    </span>
                    <ArrowRight size={12} className="text-white/30" />
                    <span className="rounded-full border border-white/10 bg-black/20 px-2 py-1 font-mono text-[10px]">
                      {String(edge.to ?? "unknown")}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-white/45">
                Mission dependencies will appear here as soon as the planner emits the graph.
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-white/8 bg-black/15 p-4">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-black tracking-[0.24em] text-white/55 uppercase">
              <Activity size={12} className="text-cyan-300" />
              Operator Diagnostics
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <MiniStat
                label="Planner lanes"
                value={String(plannerDiagnostics?.laneCount ?? mission.lanes.length)}
              />
              <MiniStat
                label="Parallel cap"
                value={String(plannerDiagnostics?.parallelLimit ?? 0)}
              />
              <MiniStat label="Policy approvals" value={String(policyCounts?.approval ?? 0)} />
              <MiniStat label="Policy blocks" value={String(policyCounts?.block ?? 0)} />
              <MiniStat label="Tools started" value={String(toolDensity?.started ?? 0)} />
              <MiniStat label="Compactions" value={String(recentCompaction.length)} />
            </div>

            {recentPolicy.length > 0 ? (
              <div className="mt-4 rounded-xl border border-white/8 bg-black/20 p-3">
                <div className="mb-2 text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
                  Recent Policy Decisions
                </div>
                <div className="space-y-2">
                  {recentPolicy.map((item, index) => (
                    <div
                      key={`${item.toolName ?? "policy"}_${index}`}
                      className="rounded-lg border border-white/8 bg-white/5 px-2.5 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-black tracking-[0.16em] text-white/45 uppercase">
                          {item.toolName || "tool"}
                        </span>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[9px] font-black uppercase ${item.decision === "block" ? "border-red-400/20 bg-red-400/10 text-red-100" : item.decision === "approval" ? "border-amber-400/20 bg-amber-400/10 text-amber-100" : "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"}`}
                        >
                          {formatCompactLabel(item.decision)}
                        </span>
                      </div>
                      <p className="mt-1 text-[12px] leading-5 text-white/72">
                        {item.reason || "Allowed without additional policy gating."}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {recentHooks.length > 0 ? (
              <div className="mt-4 rounded-xl border border-white/8 bg-black/20 p-3">
                <div className="mb-2 text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
                  Recent Hook Activity
                </div>
                <div className="space-y-2">
                  {recentHooks.map((item, index) => (
                    <div
                      key={`${item.hook ?? "hook"}_${index}`}
                      className="rounded-lg border border-white/8 bg-white/5 px-2.5 py-2 text-[12px] leading-5 text-white/72"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-black tracking-[0.16em] text-white/45 uppercase">
                          {formatCompactLabel(item.phase)}
                        </span>
                        <span className="rounded-full border border-cyan-400/15 bg-cyan-400/10 px-2 py-0.5 text-[9px] font-black text-cyan-100 uppercase">
                          {item.status || "observed"}
                        </span>
                      </div>
                      <p className="mt-1">
                        {(item.hook || "runtime hook").replace(/_/g, " ")}
                        {item.changedFields && item.changedFields.length > 0
                          ? ` changed ${item.changedFields.join(", ")}`
                          : ""}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="rounded-2xl border border-white/8 bg-black/15 p-4">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-black tracking-[0.24em] text-white/55 uppercase">
              <ShieldAlert size={12} className="text-amber-300" />
              Approval Queue
            </div>
            {mission.approvalQueue && mission.approvalQueue.length > 0 ? (
              <div className="space-y-2">
                {mission.approvalQueue.map((item, index) => (
                  <div
                    key={`${String(item.lane_id ?? "approval")}-${index}`}
                    className="rounded-xl border border-amber-400/15 bg-amber-400/8 p-3"
                  >
                    <div className="text-[10px] font-black tracking-[0.18em] text-amber-100 uppercase">
                      {String(item.lane_type ?? "lane")} · {String(item.lane_id ?? "approval")}
                    </div>
                    <p className="mt-1 text-sm leading-6 text-amber-50/85">
                      {String(item.message ?? "Approval required.")}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-white/45">No approvals are waiting right now.</p>
            )}
          </div>

          <div className="rounded-2xl border border-white/8 bg-black/15 p-4">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-black tracking-[0.24em] text-white/55 uppercase">
              <Clock3 size={12} className="text-cyan-300" />
              Mission Feed
            </div>
            <div className="space-y-2">
              {mission.globalEvents.slice(-6).map((event) => (
                <div
                  key={event.id}
                  className="rounded-xl border border-white/8 bg-white/5 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[10px] font-black tracking-[0.18em] text-white/55 uppercase">
                      {event.kind.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] text-white/30">
                      {new Date(event.at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="mt-1 text-sm leading-6 text-white/70">{event.message}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "cyan" | "emerald" | "amber" | "red";
}) {
  const toneClasses = {
    cyan: "border-cyan-400/15 bg-cyan-400/10 text-cyan-100",
    emerald: "border-emerald-400/15 bg-emerald-400/10 text-emerald-100",
    amber: "border-amber-400/15 bg-amber-400/10 text-amber-100",
    red: "border-red-400/15 bg-red-400/10 text-red-100",
  } as const;

  return (
    <div className={`rounded-2xl border px-3 py-2 ${toneClasses[tone]}`}>
      <div className="text-[9px] tracking-[0.18em] opacity-70">{label}</div>
      <div className="mt-1 text-lg font-black tracking-tight">{value}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/5 px-3 py-2">
      <div className="text-[9px] font-black tracking-[0.16em] text-white/35 uppercase">{label}</div>
      <div className="mt-1 text-sm font-black tracking-tight text-white/90">{value}</div>
    </div>
  );
}

function LaneCard({ lane }: { lane: MissionLaneVisual }) {
  const recentEvents = lane.events.slice(-3).reverse();
  const requestedSubagentType =
    typeof lane.metadata?.requested_subagent_type === "string"
      ? String(lane.metadata.requested_subagent_type)
      : null;
  const resolvedSubagentType =
    typeof lane.metadata?.resolved_subagent_type === "string"
      ? String(lane.metadata.resolved_subagent_type)
      : (lane.subagentType ?? null);
  const toolDensity =
    lane.metadata?.tool_density && typeof lane.metadata.tool_density === "object"
      ? (lane.metadata.tool_density as Record<string, unknown>)
      : null;
  const lifecycle =
    lane.metadata?.lane_lifecycle_summary &&
    typeof lane.metadata.lane_lifecycle_summary === "object"
      ? (lane.metadata.lane_lifecycle_summary as Record<string, unknown>)
      : null;
  const runtimeDiagnostics =
    lane.metadata?.runtime_diagnostics && typeof lane.metadata.runtime_diagnostics === "object"
      ? (lane.metadata.runtime_diagnostics as Record<string, unknown>)
      : null;
  const compactionState =
    lane.metadata?.compaction_state && typeof lane.metadata.compaction_state === "object"
      ? (lane.metadata.compaction_state as Record<string, unknown>)
      : null;

  return (
    <article className="rounded-2xl border border-white/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.07),rgba(255,255,255,0.03))] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-black/20 text-cyan-200">
              {laneIcon(lane)}
            </span>
            <div className="min-w-0">
              <h5 className="truncate text-sm font-black tracking-tight text-white/90">
                {lane.title}
              </h5>
              <p className="text-[10px] font-bold tracking-[0.18em] text-white/35 uppercase">
                {lane.laneType}
                {lane.subagentType ? ` · ${lane.subagentType}` : ""}
              </p>
            </div>
          </div>
        </div>

        <span
          className={`rounded-full border px-2.5 py-1 text-[10px] font-black tracking-[0.18em] uppercase ${statusClass(lane.status)}`}
        >
          {formatStatus(lane.status)}
        </span>
      </div>

      <p className="mt-3 line-clamp-3 text-sm leading-6 text-white/55">
        {lane.prompt || "No prompt captured for this lane."}
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {lane.dependsOn.map((dependency) => (
          <span
            key={dependency}
            className="rounded-full border border-white/10 bg-white/5 px-2 py-1 font-mono text-[10px] text-white/45"
          >
            depends on {dependency}
          </span>
        ))}
        {requestedSubagentType &&
        resolvedSubagentType &&
        requestedSubagentType !== resolvedSubagentType ? (
          <span className="rounded-full border border-cyan-400/15 bg-cyan-400/10 px-2 py-1 font-mono text-[10px] text-cyan-100/85">
            profile {requestedSubagentType} -&gt; {resolvedSubagentType}
          </span>
        ) : resolvedSubagentType ? (
          <span className="rounded-full border border-cyan-400/15 bg-cyan-400/10 px-2 py-1 font-mono text-[10px] text-cyan-100/85">
            profile {formatRuntimeProfile(resolvedSubagentType)}
          </span>
        ) : null}
        {lane.blockedBy.map((blocker) => (
          <span
            key={blocker}
            className="rounded-full border border-orange-400/15 bg-orange-400/10 px-2 py-1 font-mono text-[10px] text-orange-100/80"
          >
            blocked by {blocker}
          </span>
        ))}
        {toolDensity ? (
          <span className="rounded-full border border-emerald-400/15 bg-emerald-400/10 px-2 py-1 font-mono text-[10px] text-emerald-100/85">
            tools {Number(toolDensity.completed ?? 0)}/{Number(toolDensity.started ?? 0)}
          </span>
        ) : null}
        {compactionState ? (
          <span className="rounded-full border border-fuchsia-400/15 bg-fuchsia-400/10 px-2 py-1 font-mono text-[10px] text-fuchsia-100/85">
            compacted {Number(compactionState.saved_tokens ?? 0)} tokens
          </span>
        ) : null}
      </div>

      <div className="mt-4 grid gap-2 text-xs text-white/65">
        {typeof lane.metadata?.delegation_rationale === "string" &&
        lane.metadata.delegation_rationale.trim() ? (
          <div className="rounded-xl border border-white/8 bg-black/20 p-3">
            <div className="mb-1 text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
              Delegation rationale
            </div>
            <p className="line-clamp-3 leading-6">{lane.metadata.delegation_rationale}</p>
          </div>
        ) : null}

        {lane.summary ? (
          <div className="rounded-xl border border-white/8 bg-black/20 p-3">
            <div className="mb-1 text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
              Summary
            </div>
            <p className="line-clamp-4 leading-6">{lane.summary}</p>
          </div>
        ) : null}

        {lane.error ? (
          <div className="rounded-xl border border-red-400/15 bg-red-400/10 p-3 text-red-100/90">
            <div className="mb-1 text-[10px] font-black tracking-[0.18em] uppercase">Error</div>
            <p className="line-clamp-4 leading-6">{lane.error}</p>
          </div>
        ) : null}

        {lifecycle || runtimeDiagnostics ? (
          <div className="rounded-xl border border-white/8 bg-black/20 p-3">
            <div className="mb-2 text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
              Runtime posture
            </div>
            <div className="flex flex-wrap gap-2 text-[10px] font-bold tracking-[0.16em] text-white/52 uppercase">
              {typeof lifecycle?.status === "string" ? (
                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1">
                  lifecycle {formatCompactLabel(String(lifecycle.status))}
                </span>
              ) : null}
              {typeof lifecycle?.elapsed_ms === "number" ? (
                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1">
                  {Math.round(Number(lifecycle.elapsed_ms) / 1000)}s runtime
                </span>
              ) : null}
              {runtimeDiagnostics && typeof runtimeDiagnostics === "object" ? (
                <span className="rounded-full border border-cyan-400/15 bg-cyan-400/10 px-2 py-1 text-cyan-100/85">
                  diagnostics active
                </span>
              ) : null}
            </div>
          </div>
        ) : null}

        {recentEvents.length > 0 ? (
          <div className="rounded-xl border border-white/8 bg-black/20 p-3">
            <div className="mb-2 text-[10px] font-black tracking-[0.18em] text-white/35 uppercase">
              Latest Activity
            </div>
            <div className="space-y-2">
              {recentEvents.map((event) => (
                <div
                  key={event.id}
                  className="rounded-lg border border-white/8 bg-white/5 px-2.5 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-black tracking-[0.16em] text-white/45 uppercase">
                      {event.kind.replace(/_/g, " ")}
                    </span>
                    {event.status ? (
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[9px] font-black uppercase ${statusClass(event.status)}`}
                      >
                        {formatStatus(event.status)}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 line-clamp-3 text-[12px] leading-5 text-white/72">
                    {event.message}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {lane.completedAt ? (
          <div className="flex items-center gap-2 text-[10px] font-bold tracking-[0.18em] text-white/35 uppercase">
            <CheckCircle2 size={11} className="text-emerald-300" />
            Updated {new Date(lane.completedAt).toLocaleTimeString()}
          </div>
        ) : null}
      </div>
    </article>
  );
}
