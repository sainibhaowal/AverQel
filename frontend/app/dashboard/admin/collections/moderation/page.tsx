"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";
import toast from "react-hot-toast";

import { fetchWithAuth } from "@/lib/api";

type ReportStatus = "open" | "reviewing" | "resolved" | "dismissed";

type ModerationReport = {
  id: string;
  collection_id: string;
  reporter_user_id: string;
  reported_user_id: string | null;
  message_id: string | null;
  reason: string;
  details: string | null;
  status: ReportStatus;
  created_at: string;
  resolved_at: string | null;
};

const STATUS_OPTIONS: Array<ReportStatus | "all"> = ["open", "reviewing", "resolved", "dismissed", "all"];

export default function CollectionModerationPage() {
  const [status, setStatus] = useState<ReportStatus | "all">("open");
  const [reports, setReports] = useState<ModerationReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const response = (await fetchWithAuth(
        `/collections/admin/security/reports?status=${status}&limit=100`,
      )) as Response;
      if (!response.ok) throw new Error("Moderation reports could not be loaded.");
      setReports((await response.json()) as ModerationReport[]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Moderation reports could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    queueMicrotask(() => void loadReports());
  }, [loadReports]);

  const updateReport = async (report: ModerationReport, nextStatus: ReportStatus) => {
    setUpdatingId(report.id);
    try {
      const response = (await fetchWithAuth(`/collections/admin/security/reports/${report.id}`, {
        method: "POST",
        body: JSON.stringify({ status: nextStatus }),
      })) as Response;
      if (!response.ok) throw new Error("Moderation report could not be updated.");
      const updated = (await response.json()) as ModerationReport;
      setReports((current) => (status === "all" ? current.map((item) => (item.id === updated.id ? updated : item)) : current.filter((item) => item.id !== updated.id)));
      toast.success(`Report marked ${nextStatus}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Moderation update failed.");
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 p-6 lg:p-10">
      <section className="rounded-2xl border border-cyan-200/30 bg-white/70 p-6 shadow-sm dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-300">
              <ShieldAlert size={15} /> Collection security
            </p>
            <h1 className="text-2xl font-black text-slate-900 dark:text-white">Moderation queue</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600 dark:text-slate-300">
              Review reports across this workspace. Collection membership and tenant isolation are enforced by the API.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadReports()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-cyan-300/60 px-4 py-2 text-sm font-semibold text-cyan-800 disabled:opacity-50 dark:text-cyan-200"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-cyan-200/30 bg-white/70 p-6 shadow-sm dark:border-white/10 dark:bg-white/[0.04]">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value as ReportStatus | "all")}
              className="rounded-xl border border-cyan-200 bg-white px-3 py-2 text-sm dark:border-white/15 dark:bg-slate-950"
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>{option[0].toUpperCase() + option.slice(1)}</option>
              ))}
            </select>
          </label>
          <span className="text-sm text-slate-500 dark:text-slate-400">{reports.length} report{reports.length === 1 ? "" : "s"}</span>
        </div>

        {loading ? (
          <p className="py-12 text-center text-sm text-slate-500">Loading moderation reports…</p>
        ) : reports.length === 0 ? (
          <p className="py-12 text-center text-sm text-slate-500">No reports in this view.</p>
        ) : (
          <div className="space-y-3">
            {reports.map((report) => (
              <article key={report.id} className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-950/40">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-900 dark:text-white">{report.reason}</p>
                    <p className="mt-1 text-xs text-slate-500">Collection {report.collection_id} · {new Date(report.created_at).toLocaleString()}</p>
                    {report.reported_user_id && <p className="mt-1 text-xs text-slate-500">Reported user: {report.reported_user_id}</p>}
                  </div>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold uppercase tracking-wide text-slate-600 dark:bg-white/10 dark:text-slate-300">{report.status}</span>
                </div>
                {report.details && <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{report.details}</p>}
                {report.status !== "resolved" && report.status !== "dismissed" && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button type="button" disabled={updatingId === report.id} onClick={() => void updateReport(report, "reviewing")} className="rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-semibold text-amber-800 disabled:opacity-50 dark:text-amber-200">Mark reviewing</button>
                    <button type="button" disabled={updatingId === report.id} onClick={() => void updateReport(report, "resolved")} className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">Resolve</button>
                    <button type="button" disabled={updatingId === report.id} onClick={() => void updateReport(report, "dismissed")} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-50 dark:border-white/20 dark:text-slate-200">Dismiss</button>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
