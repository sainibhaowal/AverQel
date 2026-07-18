"use client";

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

interface VolumePoint {
  date: string;
  count: number;
}

interface ConfDist {
  high: number;
  medium: number;
  low: number;
}

interface AnalyticsData {
  total_queries: number;
  avg_confidence: number;
  volume_over_time: VolumePoint[];
  confidence_distribution: ConfDist;
  api_latency_p95_ms: number | null;
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const res = (await fetchWithAuth("/analytics/dashboard")) as Response;
        if (res.ok) {
          const json = await res.json();
          setData(json);
          setError(null);
        } else {
          setData(null);
          setError(
            res.status === 401
              ? "Session expired. Redirecting to login..."
              : "Failed to load analytics.",
          );
        }
      } catch (error) {
        console.error(error);
        setData(null);
        setError("Failed to load analytics.");
      } finally {
        setLoading(false);
      }
    };
    fetchAnalytics();
  }, []);

  if (loading) {
    return <div className="text-muted-foreground px-6 py-6">Loading analytics...</div>;
  }

  if (!data) {
    return (
      <div className="text-muted-foreground px-6 py-6">{error ?? "Failed to load analytics."}</div>
    );
  }

  const {
    total_queries,
    avg_confidence,
    volume_over_time,
    confidence_distribution,
    api_latency_p95_ms,
  } = data;
  const latencyDisplay =
    api_latency_p95_ms === null || api_latency_p95_ms === undefined
      ? null
      : api_latency_p95_ms >= 1000
        ? `${(api_latency_p95_ms / 1000).toFixed(2)}s`
        : `${Math.round(api_latency_p95_ms)}ms`;
  const totalInDist =
    confidence_distribution.high + confidence_distribution.medium + confidence_distribution.low ||
    1;

  const pctHigh = Math.round((confidence_distribution.high / totalInDist) * 100);
  const pctMedium = Math.round((confidence_distribution.medium / totalInDist) * 100);
  const pctLow = Math.round((confidence_distribution.low / totalInDist) * 100);
  const maxVolume = Math.max(...volume_over_time.map((point) => point.count), 1);

  return (
    <div className="w-full space-y-8">
      <DashboardSectionHeader
        title="Analytics & Telemetry"
        subtitle="System Activity And Usage Trends"
        icon={Activity}
        accentClassName="bg-emerald-500 text-emerald-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(16,185,129,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
      />

      <div
        className={`grid gap-5 ${latencyDisplay !== null ? "md:grid-cols-3" : "md:grid-cols-2"}`}
      >
        <MetricCard
          label="Total Queries"
          value={String(total_queries)}
          valueClassName="text-primary dark:text-primary"
        />
        <MetricCard
          label="System Confidence Avg"
          value={avg_confidence.toFixed(2)}
          valueClassName="text-primary dark:text-primary"
        />
        {latencyDisplay !== null ? (
          <MetricCard
            label="API Latency (p95)"
            value={latencyDisplay}
            valueClassName="text-rose-700 dark:text-rose-300"
          />
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="theme-panel rounded-[1.5rem] p-5">
          <h2 className="text-foreground text-lg font-semibold">Query Volume (Last 30 Days)</h2>
          <div className="border-glass-border mt-5 flex h-[220px] items-end gap-2 border-b pb-4">
            {volume_over_time.length === 0 ? (
              <div className="text-muted-foreground m-auto text-sm">No data</div>
            ) : (
              volume_over_time.map((point) => (
                <div key={point.date} className="flex flex-1 flex-col items-center justify-end">
                  <div
                    title={`${point.date}: ${point.count}`}
                    className="bg-primary w-full rounded-t-md"
                    style={{
                      height: `${(point.count / maxVolume) * 100}%`,
                      minHeight: point.count > 0 ? "4px" : "0",
                    }}
                  />
                </div>
              ))
            )}
          </div>
        </section>

        <section className="theme-panel rounded-[1.5rem] p-5">
          <h2 className="text-foreground text-lg font-semibold">Confidence Distribution</h2>
          <div className="mt-5 space-y-5">
            <ProgressRow
              label="High (≥80%)"
              value={pctHigh}
              count={confidence_distribution.high}
              barClassName="bg-primary"
            />
            <ProgressRow
              label="Medium (50-79%)"
              value={pctMedium}
              count={confidence_distribution.medium}
              barClassName="bg-amber-500"
            />
            <ProgressRow
              label="Low (<50%)"
              value={pctLow}
              count={confidence_distribution.low}
              barClassName="bg-red-500"
            />
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName: string;
}) {
  return (
    <div className="theme-panel rounded-[1.35rem] p-5">
      <div className="text-muted-foreground text-sm">{label}</div>
      <div className={`mt-2 text-4xl font-semibold tracking-tight ${valueClassName}`}>{value}</div>
    </div>
  );
}

function ProgressRow({
  label,
  value,
  count,
  barClassName,
}: {
  label: string;
  value: number;
  count: number;
  barClassName: string;
}) {
  return (
    <div>
      <div className="text-foreground/82 mb-2 flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground">
          {value}% ({count})
        </span>
      </div>
      <div className="bg-foreground/[0.08] h-2 overflow-hidden rounded-full dark:bg-white/8">
        <div className={`h-full ${barClassName}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
