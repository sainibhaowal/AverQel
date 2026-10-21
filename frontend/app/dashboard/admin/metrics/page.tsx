"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Activity,
  Database,
  Server,
  RefreshCcw,
  ActivitySquare,
  Cpu,
  FileDigit,
  ShieldCheck,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import AverQelLoading from "@/app/components/ui/AverQelLoading";
import { readServerSentEvents } from "./metricsStream";

interface MetricsSummary {
  api_requests_total: number;
  api_errors_total: number;
  db_query_count: number;
  worker_retries_total: number;
  worker_dead_letters_total: number;
  deepspace_cache_reads_total: number;
  deepspace_cache_writes_total: number;
  deepspace_context_compactions_total: number;
  deepspace_overflow_prevented_total: number;
  deepspace_mcp_result_references_total: number;
  deepspace_budget_allocations_total: number;
  deepspace_result_reference_events_total: number;
  deepspace_execution_batches_total: number;
  deepspace_canary_mismatches_total: number;
  metrics_scope: "service-wide";
  metrics_complete: boolean;
  metrics_started_at: string;
  snapshot_at: string;
}

interface Capabilities {
  supported_formats: Array<{ extension: string; category: string }>;
  ocr_enabled: boolean;
  vision_enabled: boolean;
  limits: {
    max_pdf_pages: number;
    max_text_chars: number;
  };
}

export default function MetricsPage() {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilitiesStatus, setCapabilitiesStatus] = useState<
    "loading" | "available" | "unavailable"
  >("loading");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState<
    "connecting" | "live" | "reconnecting" | "partial"
  >("connecting");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const summaryRes = (await fetchWithAuth("/metrics/summary")) as Response;

      if (!summaryRes.ok) {
        setError(
          summaryRes.status === 401
            ? "Session expired. Redirecting to login..."
            : summaryRes.status === 403
              ? "Admin access required to view metrics."
              : "Failed to load metrics.",
        );
        setStreamStatus("reconnecting");
        return;
      }

      const next = (await summaryRes.json()) as MetricsSummary;
      setSummary(next);
      setLastUpdated(new Date(next.snapshot_at));
      setStreamStatus(next.metrics_complete ? "live" : "partial");
      setError(null);
    } catch (e) {
      console.error("Failed to fetch metrics", e);
      setError("Live metrics could not be refreshed. Showing the last received snapshot.");
      setStreamStatus("reconnecting");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    let streamController: AbortController | null = null;

    const loadCapabilities = async () => {
      try {
        const response = (await fetchWithAuth("/capabilities")) as Response;
        if (!response.ok) {
          setCapabilitiesStatus("unavailable");
          return;
        }
        const next = (await response.json()) as Capabilities;
        if (active) {
          setCapabilities(next);
          setCapabilitiesStatus("available");
        }
      } catch {
        if (active) {
          setCapabilitiesStatus("unavailable");
        }
      }
    };

    const connectMetricsStream = async () => {
      let retryDelayMs = 1_000;
      while (active) {
        streamController = new AbortController();
        setStreamStatus((current) =>
          current === "live" || current === "partial" ? "reconnecting" : current,
        );
        try {
          const response = (await fetchWithAuth("/metrics/summary/stream", {
            headers: { Accept: "text/event-stream" },
            signal: streamController.signal,
            timeoutMs: 30_000,
            silentTimeout: true,
          })) as Response;
          if (!response.ok || !response.body) {
            if (response.status === 401) {
              throw new Error("Your session expired. Sign in again to view live metrics.");
            }
            if (response.status === 403) {
              throw new Error("Platform administrator access is required to view metrics.");
            }
            throw new Error("The shared metrics stream is temporarily unavailable.");
          }

          retryDelayMs = 1_000;
          for await (const message of readServerSentEvents(response.body)) {
            if (!active) {
              break;
            }
            if (message.event === "metrics") {
              const next = JSON.parse(message.data) as MetricsSummary;
              setSummary(next);
              setLoading(false);
              setLastUpdated(new Date(next.snapshot_at));
              setStreamStatus(next.metrics_complete ? "live" : "partial");
              setError(
                next.metrics_complete
                  ? null
                  : "Some counter updates were missed while shared metrics storage was unavailable.",
              );
            } else if (message.event === "metrics_status") {
              setStreamStatus("reconnecting");
              setError(
                "Shared metrics storage is unavailable. Keeping the last received snapshot.",
              );
            }
          }
        } catch (streamError) {
          if (!active || streamController.signal.aborted) {
            break;
          }
          setStreamStatus("reconnecting");
          setError(
            streamError instanceof Error
              ? streamError.message
              : "The live metrics connection was interrupted.",
          );
        }

        if (active) {
          await new Promise((resolve) => window.setTimeout(resolve, retryDelayMs));
          retryDelayMs = Math.min(retryDelayMs * 2, 10_000);
        }
      }
    };

    void loadCapabilities();
    void connectMetricsStream();

    return () => {
      active = false;
      streamController?.abort();
    };
  }, []);

  const statusLabel =
    streamStatus === "live"
      ? "Live · service-wide"
      : streamStatus === "partial"
        ? "Partial data"
        : streamStatus === "connecting"
          ? "Connecting…"
          : "Reconnecting…";

  return (
    <div className="space-y-8 pb-10">
      <DashboardSectionHeader
        title="System Metrics"
        subtitle="Live Service Activity Counters"
        icon={ActivitySquare}
        accentClassName="bg-violet-500 text-violet-400"
        accentGlowClassName="shadow-[0_0_18px_rgba(139,92,246,0.28)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
        actions={
          <>
            <div className="text-muted-foreground flex flex-col text-right font-mono text-xs">
              <span>{statusLabel}</span>
              <span>
                {lastUpdated
                  ? `Last counter change ${lastUpdated.toLocaleTimeString()}`
                  : "Waiting for first snapshot"}
              </span>
              {summary?.metrics_started_at ? (
                <span>Tracking since {new Date(summary.metrics_started_at).toLocaleString()}</span>
              ) : null}
            </div>
            <button
              onClick={fetchMetrics}
              disabled={loading}
              className="bg-muted border-glass-border text-muted-foreground hover:text-foreground flex items-center gap-2 rounded-xl border p-2.5 text-sm font-bold transition-all"
            >
              <RefreshCcw size={16} className={loading ? "animate-spin" : ""} />
              Refresh Snapshot
            </button>
          </>
        }
      />

      {error ? (
        <div className="rounded-[1.35rem] border border-red-400/24 bg-red-400/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <div className="glass-card border-l-primary hover:border-l-primary/80 border-l-4 p-6">
            <div className="mb-4 flex items-start justify-between">
              <div className="bg-primary/10 text-primary rounded-xl p-3">
                <Server size={20} />
              </div>
              <span className="bg-primary/10 text-primary rounded-md px-2 py-1 text-[10px] font-bold tracking-wider uppercase">
                {summary ? (summary.metrics_complete ? "Complete" : "Partial") : "Waiting"}
              </span>
            </div>
            <h3 className="mb-1 text-sm font-semibold tracking-wider text-slate-400 uppercase">
              Service HTTP Requests
            </h3>
            <p className="text-foreground font-mono text-4xl font-black">
              {summary ? summary.api_requests_total.toLocaleString() : "--"}
            </p>
          </div>

          <div className="glass-card border-l-4 border-l-green-500 p-6 hover:border-l-green-400">
            <div className="mb-4 flex items-start justify-between">
              <div className="rounded-xl bg-green-500/10 p-3 text-green-500">
                <Database size={20} />
              </div>
              <span className="rounded-md bg-green-500/10 px-2 py-1 text-[10px] font-bold tracking-wider text-green-500 uppercase">
                PostgreSQL
              </span>
            </div>
            <h3 className="mb-1 text-sm font-semibold tracking-wider text-slate-400 uppercase">
              Instrumented DB Operations
            </h3>
            <p className="text-foreground font-mono text-4xl font-black">
              {summary ? summary.db_query_count.toLocaleString() : "--"}
            </p>
          </div>

          <div className="glass-card border-l-4 border-l-red-500 p-6 hover:border-l-red-400">
            <div className="mb-4 flex items-start justify-between">
              <div className="rounded-xl bg-red-500/10 p-3 text-red-500">
                <Activity size={20} />
              </div>
              <span className="rounded-md bg-red-500/10 px-2 py-1 text-[10px] font-bold tracking-wider text-red-500 uppercase">
                Errors
              </span>
            </div>
            <h3 className="mb-1 text-sm font-semibold tracking-wider text-slate-400 uppercase">
              HTTP Error Responses
            </h3>
            <p className="text-foreground font-mono text-4xl font-black">
              {summary ? summary.api_errors_total.toLocaleString() : "--"}
            </p>
          </div>

          <div className="glass-card border-l-4 border-l-amber-500 p-6 hover:border-l-amber-400">
            <h3 className="mb-1 text-sm font-semibold tracking-wider text-slate-400 uppercase">
              Library Worker Retries
            </h3>
            <p className="text-foreground font-mono text-4xl font-black">
              {summary ? summary.worker_retries_total.toLocaleString() : "--"}
            </p>
          </div>
          <div className="glass-card border-l-4 border-l-rose-500 p-6 hover:border-l-rose-400">
            <h3 className="mb-1 text-sm font-semibold tracking-wider text-slate-400 uppercase">
              Library Dead Letters
            </h3>
            <p className="text-foreground font-mono text-4xl font-black">
              {summary ? summary.worker_dead_letters_total.toLocaleString() : "--"}
            </p>
          </div>
        </div>

        <section className="glass-card space-y-4 p-6">
          <div>
            <h2 className="text-lg font-bold">DeepSpace Runtime Activity</h2>
            <p className="text-muted-foreground text-xs">
              Live service-wide counts from DeepSpace and instrumented workers, cumulative from the
              tracking start time.
            </p>
          </div>
          <div className="runtime-monitoring-grid">
            {[
              ["Provider cache read events", summary?.deepspace_cache_reads_total],
              ["Provider cache write events", summary?.deepspace_cache_writes_total],
              ["Context compactions", summary?.deepspace_context_compactions_total],
              ["Context overflows prevented", summary?.deepspace_overflow_prevented_total],
              ["MCP result references created", summary?.deepspace_mcp_result_references_total],
              ["Context budget allocations", summary?.deepspace_budget_allocations_total],
              ["Stored tool result references", summary?.deepspace_result_reference_events_total],
              ["Tool batches planned", summary?.deepspace_execution_batches_total],
              ["Tool profile mismatches", summary?.deepspace_canary_mismatches_total],
            ].map(([label, value]) => (
              <div
                key={String(label)}
                className="runtime-monitoring-card min-w-0 overflow-hidden rounded-2xl border border-white/5 bg-white/5 p-3 sm:p-4"
              >
                <p className="runtime-monitoring-label text-muted-foreground font-bold tracking-[0.12em] uppercase">
                  {label}
                </p>
                <p className="runtime-monitoring-value text-foreground mt-2 font-mono font-black">
                  {typeof value === "number" ? value.toLocaleString() : "--"}
                </p>
              </div>
            ))}
          </div>
        </section>

        <div className="glass-card from-primary/5 flex flex-col gap-8 bg-gradient-to-br to-purple-500/5 p-6 sm:p-8 md:flex-row md:items-center">
          <div className="min-w-0 flex-1 space-y-4">
            <h2 className="flex min-w-0 items-center gap-2 text-xl font-bold">
              <Cpu className="text-primary" size={24} />
              Pipeline Configuration
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
              <div className="min-w-0 rounded-2xl border border-white/5 bg-white/5 p-4">
                <p className="mb-1 text-[10px] font-bold tracking-[0.16em] text-slate-500 uppercase">
                  Supported Formats
                </p>
                <p className="truncate text-xl font-black text-white sm:text-2xl">
                  {capabilities?.supported_formats.length ?? "--"}
                </p>
              </div>
              <div className="min-w-0 rounded-2xl border border-white/5 bg-white/5 p-4">
                <p className="mb-1 text-[10px] font-bold tracking-[0.16em] text-slate-500 uppercase">
                  OCR Engine
                </p>
                <p
                  className={`flex min-w-0 flex-col items-start gap-1 text-lg leading-tight font-black sm:text-xl ${capabilities?.ocr_enabled ? "text-green-500" : "text-slate-600"}`}
                >
                  <ShieldCheck size={18} className="shrink-0" />
                  <span className="min-w-0 break-words">
                    {capabilities?.ocr_enabled ? "Enabled" : "Disabled"}
                  </span>
                </p>
              </div>
              <div className="min-w-0 rounded-2xl border border-white/5 bg-white/5 p-4">
                <p className="mb-1 text-[10px] font-bold tracking-[0.16em] text-slate-500 uppercase">
                  Vision Engine
                </p>
                <p
                  className={`flex min-w-0 flex-col items-start gap-1 text-lg leading-tight font-black sm:text-xl ${capabilities?.vision_enabled ? "text-purple-500" : "text-slate-600"}`}
                >
                  <Activity size={18} className="shrink-0" />
                  <span className="min-w-0 break-words">
                    {capabilities?.vision_enabled ? "Enabled" : "Disabled"}
                  </span>
                </p>
              </div>
              <div className="min-w-0 rounded-2xl border border-white/5 bg-white/5 p-4">
                <p className="mb-1 text-[10px] font-bold tracking-[0.16em] text-slate-500 uppercase">
                  Max Pages
                </p>
                <p className="truncate text-xl font-black text-white sm:text-2xl">
                  {capabilities?.limits.max_pdf_pages ?? "--"}
                </p>
              </div>
            </div>
          </div>
          <div className="border-primary/20 bg-primary/10 flex w-full flex-col items-center justify-center rounded-3xl border p-6 text-center md:w-64">
            <div className="bg-primary/20 text-primary mb-4 rounded-2xl p-4">
              <FileDigit size={32} />
            </div>
            <p className="text-primary/90 mb-1 text-sm font-bold">Configuration Status</p>
            <p className="text-primary/60 text-[10px] font-black uppercase">
              {capabilitiesStatus === "available" ? (
                "Loaded from API"
              ) : capabilitiesStatus === "loading" ? (
                <AverQelLoading size="inline" label="Loading capabilities" />
              ) : (
                "Unavailable"
              )}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
