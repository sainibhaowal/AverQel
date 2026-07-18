"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState } from "react";

import type { QueryStatusEntry } from "../_lib/stream-protocol";

interface StatusHistoryPanelProps {
  entries: QueryStatusEntry[];
  isStreaming?: boolean;
}

function stateClasses(state: StatusHistoryPanelProps["entries"][number]["state"]): string {
  switch (state) {
    case "completed":
      return "border-emerald-500/25 bg-emerald-500/10 text-emerald-500";
    case "error":
      return "border-red-500/25 bg-red-500/10 text-red-500";
    case "pending":
      return "border-amber-500/25 bg-amber-500/10 text-amber-500";
    default:
      return "border-primary/25 bg-primary/10 text-primary";
  }
}

function formatTimestamp(value?: string): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function formatDuration(durationMs?: number): string | null {
  if (typeof durationMs !== "number" || durationMs < 0) {
    return null;
  }
  if (durationMs < 1000) {
    return `${Math.round(durationMs)} ms`;
  }
  return `${(durationMs / 1000).toFixed(2)} s`;
}

function mergeTimelineEntries(entries: QueryStatusEntry[]): QueryStatusEntry[] {
  const merged: QueryStatusEntry[] = [];

  for (const entry of entries) {
    const previous = merged[merged.length - 1];
    if (!previous) {
      merged.push(entry);
      continue;
    }

    if ((previous.code ?? previous.label) === (entry.code ?? entry.label)) {
      merged[merged.length - 1] = {
        ...entry,
        timestamp: entry.timestamp ?? previous.timestamp,
        detail: entry.detail ?? previous.detail,
        durationMs: entry.durationMs ?? previous.durationMs,
      };
      continue;
    }

    merged.push(entry);
  }

  return merged;
}

function summarizeTimeline(entries: QueryStatusEntry[]): {
  totalSteps: number;
  completedSteps: number;
  totalDurationMs: number | null;
  latestLabel: string | null;
  latestState: QueryStatusEntry["state"] | null;
} {
  const completedSteps = entries.filter((entry) => entry.state === "completed").length;
  const totalDurationMs = entries.reduce<number | null>((total, entry) => {
    if (typeof entry.durationMs !== "number" || entry.durationMs < 0) {
      return total;
    }
    return (total ?? 0) + entry.durationMs;
  }, null);
  const latest = entries[entries.length - 1] ?? null;

  return {
    totalSteps: entries.length,
    completedSteps,
    totalDurationMs,
    latestLabel: latest?.label ?? null,
    latestState: latest?.state ?? null,
  };
}

export default function StatusHistoryPanel({
  entries,
  isStreaming = false,
}: StatusHistoryPanelProps) {
  const mergedEntries = useMemo(() => mergeTimelineEntries(entries), [entries]);
  const hasError = mergedEntries.some((entry) => entry.state === "error");
  const shouldDefaultExpand = isStreaming || hasError || mergedEntries.length <= 2;
  const [userExpanded, setUserExpanded] = useState<boolean | null>(null);

  const summary = useMemo(() => summarizeTimeline(mergedEntries), [mergedEntries]);
  const latestEntry = mergedEntries[mergedEntries.length - 1] ?? null;
  const totalDurationLabel = formatDuration(summary.totalDurationMs ?? undefined);
  const latestTimeLabel = formatTimestamp(latestEntry?.timestamp);
  const expanded = userExpanded ?? shouldDefaultExpand;

  if (entries.length === 0) {
    return null;
  }

  return (
    <section className="theme-panel rounded-[1.7rem] px-4 py-4 sm:px-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-foreground/66 flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase">
            Status Timeline
          </div>
          <div className="text-foreground/48 mt-2 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="rounded-full border border-white/10 px-2 py-0.5">
              {summary.totalSteps} {summary.totalSteps === 1 ? "step" : "steps"}
            </span>
            {summary.latestLabel ? (
              <span className="rounded-full border border-white/10 px-2 py-0.5">
                Latest: {summary.latestLabel}
              </span>
            ) : null}
            {totalDurationLabel ? (
              <span className="rounded-full border border-white/10 px-2 py-0.5">
                Total {totalDurationLabel}
              </span>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setUserExpanded(!expanded)}
          className="text-foreground/72 hover:text-foreground inline-flex shrink-0 items-center gap-1 rounded-full border border-white/10 px-3 py-1.5 text-[11px] font-medium transition"
          aria-expanded={expanded}
        >
          <span>{expanded ? "Hide Timeline" : "View Timeline"}</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {!expanded && latestEntry ? (
        <div className="theme-code-surface rounded-[1.15rem] border px-3.5 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-foreground/88 truncate text-sm font-medium">
                {latestEntry.label}
              </div>
              <div className="text-foreground/52 mt-1 text-xs leading-5">
                {latestEntry.detail ??
                  `${summary.completedSteps} of ${summary.totalSteps} steps completed`}
              </div>
              {latestTimeLabel || totalDurationLabel ? (
                <div className="text-foreground/42 mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                  {latestTimeLabel ? <span>{latestTimeLabel}</span> : null}
                  {latestEntry.durationMs ? (
                    <span>{formatDuration(latestEntry.durationMs)}</span>
                  ) : totalDurationLabel ? (
                    <span>{totalDurationLabel}</span>
                  ) : null}
                </div>
              ) : null}
            </div>
            <span
              className={`inline-flex shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium ${stateClasses(latestEntry.state)}`}
            >
              {isStreaming && latestEntry.state === "running" ? "live" : latestEntry.state}
            </span>
          </div>
        </div>
      ) : null}

      {expanded ? (
        <div className="max-h-[18.5rem] space-y-2.5 overflow-y-auto pr-1">
          {mergedEntries.map((entry, index) => {
            const isLatest = index === mergedEntries.length - 1;
            const timeLabel = formatTimestamp(entry.timestamp);
            const durationLabel = formatDuration(entry.durationMs);
            return (
              <div
                key={`${entry.code ?? entry.label}-${entry.state}-${index}`}
                className="theme-code-surface rounded-[1.1rem] border px-3.5 py-2.5"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-foreground/42 text-[10px] font-semibold tracking-[0.18em] uppercase">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <div className="text-foreground/88 text-sm font-medium">{entry.label}</div>
                    </div>
                    {timeLabel || durationLabel ? (
                      <div className="text-foreground/42 mt-1 flex flex-wrap items-center gap-2 text-[11px]">
                        {timeLabel ? <span>{timeLabel}</span> : null}
                        {durationLabel ? <span>{durationLabel}</span> : null}
                      </div>
                    ) : null}
                    {entry.detail ? (
                      <div className="text-foreground/52 mt-1 text-xs leading-6">
                        {entry.detail}
                      </div>
                    ) : null}
                  </div>
                  <span
                    className={`inline-flex shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium ${stateClasses(entry.state)}`}
                  >
                    {isStreaming && isLatest && entry.state === "running" ? "live" : entry.state}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
