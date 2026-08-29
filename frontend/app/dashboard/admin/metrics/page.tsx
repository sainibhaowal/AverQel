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

interface MetricsSummary {
  api_requests_total: number;
  api_errors_total: number;
  db_query_count: number;
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
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, capRes] = await Promise.all([
        fetchWithAuth("/metrics/summary") as Promise<Response>,
        fetchWithAuth("/capabilities") as Promise<Response>,
      ]);

      if (!summaryRes.ok) {
        setError(
          summaryRes.status === 401
            ? "Session expired. Redirecting to login..."
            : summaryRes.status === 403
              ? "Admin access required to view metrics."
              : "Failed to load metrics.",
        );
        setSummary(null);
        setCapabilities(null);
        return;
      }

      setSummary(await summaryRes.json());
      if (capRes.ok) {
        setCapabilities(await capRes.json());
      }
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("Failed to fetch metrics", e);
      setSummary(null);
      setCapabilities(null);
      setError("Failed to load metrics.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void fetchMetrics());
    const interval = setInterval(fetchMetrics, 15000);
    return () => clearInterval(interval);
  }, [fetchMetrics]);

  return (
    <div className="space-y-8 pb-10">
      <DashboardSectionHeader
        title="System Metrics"
        subtitle="Real-Time Performance And Health"
        icon={ActivitySquare}
        accentClassName="bg-violet-500 text-violet-400"
        accentGlowClassName="shadow-[0_0_18px_rgba(139,92,246,0.28)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
        actions={
          <>
            <span className="text-muted-foreground font-mono text-xs">
              {lastUpdated ? `Last seen: ${lastUpdated.toLocaleTimeString()}` : "Connecting..."}
            </span>
            <button
              onClick={fetchMetrics}
              disabled={loading}
              className="bg-muted border-glass-border text-muted-foreground hover:text-foreground flex items-center gap-2 rounded-xl border p-2.5 text-sm font-bold transition-all"
            >
              <RefreshCcw size={16} className={loading ? "animate-spin" : ""} />
              Poll Now
            </button>
          </>
        }
      />

      {error ? (
        <div className="rounded-[1.35rem] border border-red-400/24 bg-red-400/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="glass-card border-l-primary hover:border-l-primary/80 border-l-4 p-6">
          <div className="mb-4 flex items-start justify-between">
            <div className="bg-primary/10 text-primary rounded-xl p-3">
              <Server size={20} />
            </div>
            <span className="bg-primary/10 text-primary rounded-md px-2 py-1 text-[10px] font-bold tracking-wider uppercase">
              Live
            </span>
          </div>
          <h3 className="mb-1 text-sm font-semibold tracking-wider text-slate-400 uppercase">
            Total HTTP Requests
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
            Database Queries
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
            HTTP Errors
          </h3>
          <p className="text-foreground font-mono text-4xl font-black">
            {summary ? summary.api_errors_total.toLocaleString() : "--"}
          </p>
        </div>

        <div className="glass-card from-primary/5 flex flex-col gap-8 bg-gradient-to-br to-purple-500/5 p-6 sm:p-8 md:col-span-3 md:flex-row md:items-center">
          <div className="min-w-0 flex-1 space-y-4">
            <h2 className="flex min-w-0 items-center gap-2 text-xl font-bold">
              <Cpu className="text-primary" size={24} />
              Pipeline Capabilities
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
                    {capabilities?.vision_enabled ? "High Coverage" : "Standard"}
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
            <div className="bg-primary/20 text-primary mb-4 animate-pulse rounded-2xl p-4">
              <FileDigit size={32} />
            </div>
            <p className="text-primary/90 mb-1 text-sm font-bold">Pipeline Health</p>
            <p className="text-primary/60 text-[10px] font-black uppercase">
              All Modules Operational
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
