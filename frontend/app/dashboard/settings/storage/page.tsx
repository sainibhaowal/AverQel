"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  Brain,
  ChevronDown,
  CircleDashed,
  Database,
  FileText,
  FolderTree,
  Gauge,
  HardDrive,
  ListTodo,
  Loader2,
  MessageSquare,
  Network,
  PieChart,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";
import { useRealtimeEvents } from "@/lib/realtime";

type StorageMetric = {
  key: string;
  label: string;
  description: string;
  bytes: number;
  record_count: number;
  included_in_quota: boolean;
  measurement: string;
  tokens?: number | null;
};

type StorageDetails = {
  current_plan: {
    id: string;
    name: string;
    storage_limit_bytes: number;
    description: string;
    admin_account: boolean;
  };
  usage: {
    total_bytes: number;
  };
  metrics: StorageMetric[];
  quota_metering_note: string;
  generated_at: string;
};

type StorageRetentionPolicy = {
  mode: "off" | "30" | "60" | "90";
  days: number;
  policy_version: number;
  automatic_purge_enabled: boolean;
};

const metricIcons: Record<string, typeof FileText> = {
  documents: FileText,
  library: HardDrive,
  artifacts: Sparkles,
  pending_uploads: Zap,
  chat_history: MessageSquare,
  memory: Brain,
  collections_and_index: Search,
  activity_and_runs: Activity,
  queues_and_tasks: ListTodo,
  workspace_structure: FolderTree,
  token_usage: Database,
  providers_and_connections: Network,
  grounded_queries: Search,
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${Math.max(0, bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatLimit(bytes: number): string {
  const gib = 1024 * 1024 * 1024;
  return bytes >= gib && bytes % gib === 0
    ? `${bytes / gib} GB`
    : `${Math.round(bytes / (1024 * 1024))} MB`;
}

function formatTokens(tokens: number | null | undefined): string {
  if (!tokens) return "0 tokens";
  return `${tokens.toLocaleString()} tokens`;
}

function metricPercent(metric: StorageMetric, total: number): number {
  if (!metric.bytes || total <= 0) return 0;
  return Math.min(100, (metric.bytes / total) * 100);
}

const metricColors: Record<string, { solid: string; text: string; soft: string }> = {
  documents: { solid: "#0f766e", text: "text-teal-700 dark:text-teal-300", soft: "bg-teal-500/15" },
  library: {
    solid: "#7c3aed",
    text: "text-violet-700 dark:text-violet-300",
    soft: "bg-violet-500/15",
  },
  artifacts: { solid: "#db2777", text: "text-pink-700 dark:text-pink-300", soft: "bg-pink-500/15" },
  pending_uploads: {
    solid: "#ca8a04",
    text: "text-yellow-700 dark:text-yellow-300",
    soft: "bg-yellow-500/15",
  },
  grounded_queries: {
    solid: "#16a34a",
    text: "text-green-700 dark:text-green-300",
    soft: "bg-green-500/15",
  },
  memory: { solid: "#dc2626", text: "text-red-700 dark:text-red-300", soft: "bg-red-500/15" },
  collections_and_index: {
    solid: "#4f46e5",
    text: "text-indigo-700 dark:text-indigo-300",
    soft: "bg-indigo-500/15",
  },
  activity_and_runs: {
    solid: "#be123c",
    text: "text-rose-700 dark:text-rose-300",
    soft: "bg-rose-500/15",
  },
  queues_and_tasks: {
    solid: "#ea580c",
    text: "text-orange-700 dark:text-orange-300",
    soft: "bg-orange-500/15",
  },
  workspace_structure: {
    solid: "#64748b",
    text: "text-slate-700 dark:text-slate-300",
    soft: "bg-slate-500/15",
  },
  providers_and_connections: {
    solid: "#0f766e",
    text: "text-teal-700 dark:text-teal-300",
    soft: "bg-teal-500/15",
  },
};

const fallbackMetricColor = {
  solid: "#475569",
  text: "text-slate-700 dark:text-slate-300",
  soft: "bg-slate-500/15",
};
function getMetricColor(key: string) {
  return metricColors[key] ?? fallbackMetricColor;
}

function buildUsageGradient(metrics: StorageMetric[], limit: number, used: number): string {
  if (limit <= 0 || used <= 0) return "#1e293b 0deg 360deg";
  const usedDegrees = Math.min(360, (used / limit) * 360);
  const segments: string[] = [];
  let cursor = 0;
  const meteredTotal = metrics.reduce((sum, metric) => sum + Math.max(0, metric.bytes), 0);
  const denominator = meteredTotal > 0 ? meteredTotal : used;

  for (const metric of metrics) {
    if (metric.bytes <= 0) continue;
    const next = Math.min(usedDegrees, cursor + (metric.bytes / denominator) * usedDegrees);
    segments.push(`${getMetricColor(metric.key).solid} ${cursor}deg ${next}deg`);
    cursor = next;
  }
  if (cursor < usedDegrees) segments.push(`#67e8f9 ${cursor}deg ${usedDegrees}deg`);
  segments.push(`#1e293b ${usedDegrees}deg 360deg`);
  return segments.join(", ");
}

export default function StorageDetailsPage() {
  const [data, setData] = useState<StorageDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [retention, setRetention] = useState<StorageRetentionPolicy | null>(null);
  const [retentionMode, setRetentionMode] = useState<StorageRetentionPolicy["mode"]>("off");
  const [retentionSaving, setRetentionSaving] = useState(false);
  const [retentionError, setRetentionError] = useState<string | null>(null);

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const response = (await fetchWithAuth("/storage/current")) as Response;
      if (!response.ok) throw new Error("Unable to load storage details.");
      setData((await response.json()) as StorageDetails);
      if (manual) setRefreshKey((current) => current + 1);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load storage details.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useRealtimeEvents(() => {
    void load(false);
  }, ["storage", "documents", "conversations"]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void load(), 0);
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") void load();
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.clearTimeout(initialLoad);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [load]);

  useEffect(() => {
    const loadRetention = async () => {
      try {
        const response = (await fetchWithAuth("/storage/retention")) as Response;
        if (!response.ok) throw new Error("Unable to load retention settings.");
        const policy = (await response.json()) as StorageRetentionPolicy;
        setRetention(policy);
        setRetentionMode(policy.mode);
        setRetentionError(null);
      } catch (reason) {
        setRetentionError(
          reason instanceof Error ? reason.message : "Unable to load retention settings.",
        );
      }
    };
    const initialLoad = window.setTimeout(() => void loadRetention(), 0);
    return () => window.clearTimeout(initialLoad);
  }, []);

  const saveRetention = useCallback(async () => {
    setRetentionSaving(true);
    try {
      const response = (await fetchWithAuth("/storage/retention", {
        method: "PUT",
        body: JSON.stringify({ mode: retentionMode }),
      })) as Response;
      if (!response.ok) throw new Error("Unable to save retention settings.");
      const policy = (await response.json()) as StorageRetentionPolicy;
      setRetention(policy);
      setRetentionMode(policy.mode);
      setRetentionError(null);
    } catch (reason) {
      setRetentionError(
        reason instanceof Error ? reason.message : "Unable to save retention settings.",
      );
    } finally {
      setRetentionSaving(false);
    }
  }, [retentionMode]);

  const metered = useMemo(
    () => data?.metrics.filter((metric) => metric.included_in_quota) ?? [],
    [data],
  );
  const informational = useMemo(
    () => data?.metrics.filter((metric) => !metric.included_in_quota) ?? [],
    [data],
  );
  const usagePercent = data
    ? Math.min(100, (data.usage.total_bytes / data.current_plan.storage_limit_bytes) * 100)
    : 0;

  return (
    <div className="w-full space-y-8">
      <DashboardSectionHeader
        title="Storage details"
        subtitle="Live tenant storage inventory across your AverQel account"
        icon={Database}
        accentClassName="bg-cyan-500 text-cyan-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(6,182,212,0.35)]"
        backHref="/dashboard/settings/plan"
        backLabel="Back"
        actions={
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={loading || refreshing}
            className="border-border/70 bg-card/50 text-muted-foreground hover:text-foreground inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-bold transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} />
            Refresh now
          </button>
        }
      />

      {loading && (
        <div className="settings-featured text-muted-foreground flex items-center gap-3 p-7 text-sm">
          <Loader2 size={18} /> Loading storage inventory…
        </div>
      )}
      {error && (
        <div className="settings-featured text-destructive flex items-center gap-3 p-7 text-sm">
          <AlertCircle size={18} /> {error}
        </div>
      )}

      {data && (
        <>
          <section className="settings-featured overflow-hidden p-7">
            <div className="relative z-[1] grid gap-7 lg:grid-cols-[1fr_1.35fr] lg:items-center">
              <div>
                <div className="mb-3 flex items-center gap-2 text-xs font-bold tracking-[0.2em] text-cyan-600 uppercase dark:text-cyan-300">
                  <ShieldCheck size={15} /> {data.current_plan.name} plan
                </div>
                <h2 className="text-foreground text-3xl font-black tracking-tight">
                  {formatBytes(data.usage.total_bytes)}{" "}
                  <span className="text-muted-foreground text-lg">
                    of {formatLimit(data.current_plan.storage_limit_bytes)}
                  </span>
                </h2>
                <p className="text-muted-foreground mt-2 text-sm leading-6">
                  This meter is shared across the authenticated tenant/workspace. It updates
                  automatically when workspace data changes and when you return to the tab.
                </p>
              </div>
              <div className="border-border/70 bg-background/45 rounded-2xl border p-5">
                <div className="mb-3 flex items-center justify-between text-sm font-semibold">
                  <span>Quota usage</span>
                  <span
                    className={usagePercent >= 90 ? "text-destructive" : "text-muted-foreground"}
                  >
                    {usagePercent.toFixed(1)}%
                  </span>
                </div>
                <div className="bg-muted/60 h-4 overflow-hidden rounded-full">
                  <div
                    className={`h-full rounded-full ${usagePercent >= 90 ? "bg-destructive" : "bg-cyan-500"}`}
                    style={{ width: `${usagePercent}%` }}
                  />
                </div>
                <div className="text-muted-foreground mt-4 flex flex-wrap gap-3 text-xs">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-cyan-500" /> Counts toward plan
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-violet-400" /> Informational
                    inventory
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-slate-400" /> Protected metadata
                  </span>
                </div>
              </div>
            </div>
          </section>

          <div className="text-muted-foreground rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.06] p-4 text-sm leading-6">
            <div className="flex gap-3">
              <InfoIcon /> <span>{data.quota_metering_note}</span>
            </div>
          </div>

          <section
            className="settings-featured overflow-hidden p-6"
            aria-labelledby="storage-retention-policy"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs font-bold tracking-[0.18em] text-violet-600 uppercase dark:text-violet-300">
                  <ShieldCheck size={15} /> Storage lifecycle policy
                </div>
                <h2
                  id="storage-retention-policy"
                  className="text-foreground mt-2 text-xl font-black tracking-tight"
                >
                  Remove only data that has not been meaningfully used
                </h2>
                <p className="text-muted-foreground mt-1 max-w-3xl text-sm leading-6">
                  This is one tenant-scoped setting for quota-linked user content. Background
                  refreshes do not reset the timer. Active runs, queues, uploads, provider
                  credentials, security records, and unknown legacy data stay protected.
                </p>
              </div>
              <span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-300">
                Archive-first · purge disabled
              </span>
            </div>
            <div className="mt-5 flex flex-wrap items-end gap-3">
              <label
                className="text-muted-foreground grid gap-2 text-xs font-bold"
                htmlFor="storage-retention-mode"
              >
                Inactivity period
                <select
                  id="storage-retention-mode"
                  value={retentionMode}
                  onChange={(event) =>
                    setRetentionMode(event.target.value as StorageRetentionPolicy["mode"])
                  }
                  disabled={retentionSaving || !retention}
                  className="border-border/70 bg-background/70 text-foreground min-w-44 rounded-xl border px-3 py-2.5 text-sm font-semibold outline-none focus:border-cyan-500"
                >
                  <option value="off">Off</option>
                  <option value="30">30 days</option>
                  <option value="60">60 days</option>
                  <option value="90">90 days</option>
                </select>
              </label>
              <button
                type="button"
                onClick={() => void saveRetention()}
                disabled={retentionSaving || !retention || retentionMode === retention.mode}
                className="rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-black text-slate-950 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {retentionSaving ? "Saving…" : "Save policy"}
              </button>
              <span className="text-muted-foreground text-xs">
                {retention?.mode === "off"
                  ? "No automatic candidates are created."
                  : `Eligible after ${retention?.days} days of no meaningful activity.`}
              </span>
            </div>
            {retentionError && (
              <p className="text-destructive mt-3 text-xs font-semibold">{retentionError}</p>
            )}
          </section>

          <StorageVisualization
            key={refreshKey}
            data={data}
            metered={metered}
            usagePercent={usagePercent}
          />

          <section className="space-y-4">
            <div>
              <h2 className="text-foreground text-xl font-black tracking-tight">
                Storage used by category
              </h2>
              <p className="text-muted-foreground mt-1 text-sm">
                Expand any row to see its measurement, records, and quota status.
              </p>
            </div>
            <div className="grid gap-3">
              {metered.map((metric) => (
                <MetricRow key={metric.key} metric={metric} total={data.usage.total_bytes} />
              ))}
            </div>
          </section>

          <section className="space-y-4">
            <div>
              <h2 className="text-foreground text-xl font-black tracking-tight">
                Account data inventory
              </h2>
              <p className="text-muted-foreground mt-1 text-sm">
                These durable records belong to your tenant and are included using safe logical byte
                estimates where possible.
              </p>
            </div>
            <div className="grid gap-3">
              {informational.map((metric) => (
                <MetricRow key={metric.key} metric={metric} total={0} />
              ))}
            </div>
          </section>

          <p className="text-muted-foreground text-right text-xs">
            Last updated {new Date(data.generated_at).toLocaleTimeString()}
          </p>
        </>
      )}
    </div>
  );
}

function StorageVisualization({
  data,
  metered,
  usagePercent,
}: {
  data: StorageDetails;
  metered: StorageMetric[];
  usagePercent: number;
}) {
  const used = Math.max(0, data.usage.total_bytes);
  const limit = Math.max(0, data.current_plan.storage_limit_bytes);
  const remaining = Math.max(0, limit - used);
  const gradient = buildUsageGradient(metered, limit, used);
  const categoryTotal = metered.reduce((sum, metric) => sum + Math.max(0, metric.bytes), 0);

  return (
    <section
      className="settings-featured overflow-hidden p-6"
      aria-labelledby="storage-visual-overview"
    >
      <div className="relative z-[1] mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold tracking-[0.18em] text-cyan-600 uppercase dark:text-cyan-300">
            <PieChart size={15} /> Visual storage overview
          </div>
          <h2
            id="storage-visual-overview"
            className="text-foreground mt-2 text-xl font-black tracking-tight"
          >
            See exactly what is filling your allocation
          </h2>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm leading-6">
            Colors are consistent across the quota ring, category bar, and legend. The view
            refreshes with the live storage meter every 5 seconds.
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1.5 text-xs font-bold text-emerald-600 dark:text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-400" /> Live meter
        </span>
      </div>

      <div className="grid gap-6 xl:grid-cols-[230px_1fr] xl:items-center">
        <div className="flex justify-center">
          <div
            className="relative h-52 w-52 rounded-full shadow-[0_0_45px_rgba(34,211,238,0.12)]"
            role="img"
            aria-label={`${usagePercent.toFixed(1)} percent of storage allocation used`}
          >
            <div
              className="storage-visual-ring absolute inset-0 rounded-full p-5"
              style={{ background: `conic-gradient(${gradient})` }}
            />
            <div className="border-border/70 bg-background/95 absolute inset-5 z-[1] flex flex-col items-center justify-center rounded-full border text-center shadow-inner">
              <Gauge className="mb-2 text-cyan-300" size={22} />
              <span className="text-foreground text-3xl font-black">
                {usagePercent.toFixed(1)}%
              </span>
              <span className="text-muted-foreground mt-1 text-xs font-semibold">
                allocation used
              </span>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <VisualStat
              label="Used"
              value={formatBytes(used)}
              accent="text-cyan-300"
              icon={<Database size={15} />}
            />
            <VisualStat
              label="Available"
              value={formatBytes(remaining)}
              accent="text-emerald-300"
              icon={<CircleDashed size={15} />}
            />
            <VisualStat
              label="Allocation"
              value={formatLimit(limit)}
              accent="text-violet-300"
              icon={<HardDrive size={15} />}
            />
          </div>

          <div>
            <div className="text-muted-foreground mb-2 flex items-center justify-between text-xs font-bold">
              <span>Metered category distribution</span>
              <span>{metered.filter((metric) => metric.bytes > 0).length} active categories</span>
            </div>
            <div
              className="border-border/70 flex h-5 w-full overflow-hidden rounded-full border bg-slate-900/80"
              role="img"
              aria-label="Storage used by category"
            >
              {metered.map((metric) => {
                const width = categoryTotal > 0 ? (metric.bytes / categoryTotal) * 100 : 0;
                if (width <= 0) return null;
                return (
                  <span
                    key={metric.key}
                    className="h-full min-w-[3px]"
                    style={{
                      width: `${width}%`,
                      backgroundColor: getMetricColor(metric.key).solid,
                    }}
                    title={`${metric.label}: ${formatBytes(metric.bytes)} (${width.toFixed(1)}%)`}
                  />
                );
              })}
            </div>
            <div className="text-muted-foreground mt-2 flex items-center justify-between text-[11px]">
              <span>0 B</span>
              <span>{formatBytes(used)} metered usage</span>
            </div>
          </div>

          <div
            className="grid gap-x-5 gap-y-2 sm:grid-cols-2 lg:grid-cols-3"
            aria-label="Storage category legend"
          >
            {metered.map((metric) => {
              const color = getMetricColor(metric.key);
              const share = used > 0 ? (metric.bytes / used) * 100 : 0;
              return (
                <div
                  key={metric.key}
                  className="hover:bg-muted/50 flex min-w-0 items-center gap-2 rounded-md px-1 py-0.5 text-xs transition-colors"
                >
                  <span
                    className="ring-background h-3 w-3 shrink-0 rounded-full ring-2"
                    style={{ backgroundColor: color.solid }}
                  />
                  <span
                    className="text-muted-foreground min-w-0 flex-1 truncate font-medium"
                    title={metric.label}
                  >
                    {metric.label}
                  </span>
                  <span className="shrink-0 font-black" style={{ color: color.solid }}>
                    {share.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
          <div className="border-border/60 text-muted-foreground flex flex-wrap gap-4 border-t pt-4 text-xs">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-cyan-400" /> Metered and counts toward
              limit
            </span>
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-violet-400" /> Inventory shown separately
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function VisualStat({
  label,
  value,
  accent,
  icon,
}: {
  label: string;
  value: string;
  accent: string;
  icon: ReactNode;
}) {
  return (
    <div className="border-border/70 bg-background/35 rounded-xl border p-3">
      <div className={`mb-2 flex items-center gap-2 text-xs font-bold ${accent}`}>
        {icon}
        {label}
      </div>
      <div className="text-foreground text-lg font-black">{value}</div>
    </div>
  );
}

function InfoIcon() {
  return (
    <span className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-cyan-500/30 text-xs font-black text-cyan-600 dark:text-cyan-300">
      i
    </span>
  );
}

function MetricRow({ metric, total }: { metric: StorageMetric; total: number }) {
  const Icon = metricIcons[metric.key] ?? Database;
  const color = metric.included_in_quota
    ? getMetricColor(metric.key)
    : { solid: "#8b5cf6", text: "text-violet-700 dark:text-violet-300", soft: "bg-violet-500/15" };
  const percent = metricPercent(metric, total);
  const [open, setOpen] = useState(false);
  return (
    <div
      className={`storage-metric-row border-border/70 bg-card/35 rounded-2xl border transition-colors ${open ? "bg-card/60 border-cyan-500/30" : ""}`}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex w-full cursor-pointer items-center gap-4 p-4 text-left"
      >
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${metric.included_in_quota ? "bg-cyan-500/10 text-cyan-600 dark:text-cyan-300" : "bg-violet-500/10 text-violet-500"}`}
        >
          <Icon size={18} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="text-foreground flex flex-wrap items-center gap-2 text-sm font-bold">
            <span
              className="ring-background h-2.5 w-2.5 shrink-0 rounded-full ring-2"
              style={{ backgroundColor: color.solid }}
              aria-hidden="true"
            />
            {metric.label}
            {metric.included_in_quota ? (
              <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] font-bold text-cyan-700 uppercase dark:text-cyan-300">
                metered
              </span>
            ) : (
              <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-bold text-violet-600 uppercase dark:text-violet-300">
                inventory
              </span>
            )}
          </span>
          <span className="text-muted-foreground mt-1 block truncate text-xs">
            {metric.description}
          </span>
        </span>
        <span className="text-right">
          <span className="text-foreground block text-sm font-black">
            {formatBytes(metric.bytes)}
          </span>
          <span className="text-muted-foreground block text-xs">
            {metric.record_count.toLocaleString()} records
          </span>
        </span>
        <ChevronDown className="text-muted-foreground shrink-0" size={17} />
      </button>
      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="min-h-0 overflow-hidden">
          <div
            className={`border-border/60 text-muted-foreground grid gap-4 border-t px-4 py-4 text-xs transition-opacity duration-300 sm:grid-cols-3 ${open ? "opacity-100" : "opacity-0"}`}
          >
            <div>
              <span className="text-foreground block font-bold">Measurement</span>
              {metric.measurement}
            </div>
            <div>
              <span className="text-foreground block font-bold">Plan share</span>
              {metric.included_in_quota
                ? `${percent.toFixed(1)}% of metered usage`
                : "Not included in current plan meter"}
            </div>
            <div>
              <span className="text-foreground block font-bold">Additional metric</span>
              {metric.tokens !== undefined && metric.tokens !== null
                ? formatTokens(metric.tokens)
                : `${metric.record_count.toLocaleString()} retained records`}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
