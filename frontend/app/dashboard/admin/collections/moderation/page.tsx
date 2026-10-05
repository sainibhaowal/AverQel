"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  History,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import toast from "react-hot-toast";

import { fetchWithAuth } from "@/lib/api";
import RoundedSelect from "@/app/components/ui/RoundedSelect";

type ReportStatus = "open" | "reviewing" | "resolved" | "dismissed";
type StatusFilter = ReportStatus | "all";

type ModerationReport = {
  id: string;
  collection_id: string;
  collection_name: string | null;
  reporter_user_id: string;
  reported_user_id: string | null;
  message_id: string | null;
  reason: string;
  details: string | null;
  status: ReportStatus;
  created_at: string;
  resolved_at: string | null;
};

type ModerationAction = {
  id: string;
  report_id: string;
  actor_user_id: string | null;
  actor_role: string;
  action_type: "report_created" | "status_changed" | "note_added" | "history_baseline";
  previous_status: ReportStatus | null;
  new_status: ReportStatus | null;
  note: string | null;
  created_at: string;
};

type HistoryState = {
  items: ModerationAction[];
  total: number;
  hasMore: boolean;
  loading: boolean;
  error: string | null;
};

const PAGE_SIZE = 25;
const HISTORY_PAGE_SIZE = 25;
const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "open", label: "Open" },
  { value: "reviewing", label: "Reviewing" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
  { value: "all", label: "All statuses" },
];

function responseHeader(response: Response, name: string): string | null {
  return response.headers?.get(name) ?? null;
}

function formatAction(action: ModerationAction): string {
  if (action.action_type === "history_baseline") return "Audit history enabled";
  if (action.action_type === "report_created") return "Report submitted";
  if (action.action_type === "note_added") return "Moderator note added";
  return `Status changed${action.previous_status ? ` from ${action.previous_status}` : ""}${action.new_status ? ` to ${action.new_status}` : ""}`;
}

export default function CollectionModerationPage() {
  const [status, setStatus] = useState<StatusFilter>("open");
  const [reports, setReports] = useState<ModerationReport[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(null);
  const [historyByReport, setHistoryByReport] = useState<Record<string, HistoryState>>({});
  const [requestedReportId, setRequestedReportId] = useState<string | null>(null);

  useEffect(() => {
    const reportId = new URLSearchParams(window.location.search).get("report");
    if (!reportId) return;
    const timeoutId = window.setTimeout(() => {
      setStatus("all");
      setRequestedReportId(reportId);
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, []);

  const loadReports = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const response = (await fetchWithAuth(
        `/collections/admin/security/reports?status=${status}&limit=${PAGE_SIZE}&offset=${offset}${requestedReportId ? `&report_id=${encodeURIComponent(requestedReportId)}` : ""}`,
      )) as Response;
      if (!response.ok)
        throw new Error(`Moderation reports could not be loaded (${response.status}).`);
      setReports((await response.json()) as ModerationReport[]);
      setTotal(Number(responseHeader(response, "X-Total-Count") ?? 0));
      setHasMore(responseHeader(response, "X-Has-More") === "true");
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Moderation reports could not be loaded.";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [offset, requestedReportId, status]);

  useEffect(() => {
    queueMicrotask(() => void loadReports());
  }, [loadReports]);

  const loadHistory = useCallback(
    async (reportId: string, append: boolean) => {
      const existing = historyByReport[reportId];
      const nextOffset = append ? (existing?.items.length ?? 0) : 0;
      setHistoryByReport((current) => ({
        ...current,
        [reportId]: {
          items: current[reportId]?.items ?? [],
          total: current[reportId]?.total ?? 0,
          hasMore: current[reportId]?.hasMore ?? false,
          loading: true,
          error: null,
        },
      }));
      try {
        const response = (await fetchWithAuth(
          `/collections/admin/security/reports/${reportId}/history?limit=${HISTORY_PAGE_SIZE}&offset=${nextOffset}`,
        )) as Response;
        if (!response.ok)
          throw new Error(`Report history could not be loaded (${response.status}).`);
        const items = (await response.json()) as ModerationAction[];
        setHistoryByReport((current) => ({
          ...current,
          [reportId]: {
            items: append ? [...(current[reportId]?.items ?? []), ...items] : items,
            total: Number(responseHeader(response, "X-Total-Count") ?? items.length),
            hasMore: responseHeader(response, "X-Has-More") === "true",
            loading: false,
            error: null,
          },
        }));
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Report history could not be loaded.";
        setHistoryByReport((current) => ({
          ...current,
          [reportId]: {
            items: current[reportId]?.items ?? [],
            total: current[reportId]?.total ?? 0,
            hasMore: current[reportId]?.hasMore ?? false,
            loading: false,
            error: message,
          },
        }));
      }
    },
    [historyByReport],
  );

  useEffect(() => {
    if (!requestedReportId || loading) return;
    const report = reports.find((item) => item.id === requestedReportId);
    if (report) {
      document.getElementById(`moderation-report-${report.id}`)?.scrollIntoView?.({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [loading, reports, requestedReportId]);

  const toggleHistory = (reportId: string) => {
    if (expandedHistoryId === reportId) {
      setExpandedHistoryId(null);
      return;
    }
    setExpandedHistoryId(reportId);
    if (!historyByReport[reportId]) void loadHistory(reportId, false);
  };

  const updateReport = async (
    report: ModerationReport,
    nextStatus: ReportStatus,
    moderatorNote?: string,
  ) => {
    setUpdatingId(report.id);
    try {
      const response = (await fetchWithAuth(`/collections/admin/security/reports/${report.id}`, {
        method: "POST",
        body: JSON.stringify({ status: nextStatus, moderator_note: moderatorNote?.trim() || null }),
      })) as Response;
      if (!response.ok)
        throw new Error(`Moderation report could not be updated (${response.status}).`);
      setNoteDrafts((current) => ({ ...current, [report.id]: "" }));
      setHistoryByReport((current) => {
        const next = { ...current };
        delete next[report.id];
        return next;
      });
      toast.success(
        moderatorNote?.trim() ? "Internal note saved." : `Report marked ${nextStatus}.`,
      );
      await loadReports();
      if (expandedHistoryId === report.id) void loadHistory(report.id, false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Moderation update failed.");
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <main className="dashboard-theme-scope w-full space-y-6 p-4 sm:p-6 lg:p-8">
      <section className="theme-panel rounded-2xl p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="mb-2 flex items-center gap-2 text-xs font-bold tracking-[0.2em] text-cyan-700 uppercase dark:text-cyan-300">
              <ShieldAlert size={15} /> Collection security
            </p>
            <h1 className="text-foreground text-2xl font-black">Moderation queue</h1>
            <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
              Review member-submitted reports for this workspace. This queue shows report details
              and message references; it does not return chat message bodies.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadReports()}
            disabled={loading}
            className="border-border text-foreground hover:bg-surface-1 inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </section>

      <section className="theme-panel rounded-2xl p-4 shadow-sm sm:p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="text-foreground flex items-center gap-3 text-sm font-semibold">
            <label htmlFor="moderation-status">Status</label>
            <RoundedSelect
              label="Moderation report status"
              value={status}
              onChange={(value) => {
                setRequestedReportId(null);
                setStatus(value as StatusFilter);
                setOffset(0);
              }}
              options={STATUS_OPTIONS}
              triggerClassName="min-w-36 rounded-xl px-3 py-2 text-sm"
            />
          </div>
          <span className="text-muted-foreground text-sm" aria-live="polite">
            {total} report{total === 1 ? "" : "s"}
          </span>
        </div>

        {loading ? (
          <p className="text-muted-foreground py-12 text-center text-sm" role="status">
            Loading moderation reports…
          </p>
        ) : loadError ? (
          <div className="border-border rounded-xl border border-dashed px-4 py-10 text-center">
            <p className="text-foreground text-sm" role="alert">
              {loadError}
            </p>
            <button
              type="button"
              onClick={() => void loadReports()}
              className="border-border text-foreground mt-3 rounded-xl border px-4 py-2 text-sm font-semibold"
            >
              Try again
            </button>
          </div>
        ) : reports.length === 0 ? (
          <p className="text-muted-foreground py-12 text-center text-sm">
            No reports in this view.
          </p>
        ) : (
          <div className="space-y-3">
            {reports.map((report) => {
              const history = historyByReport[report.id];
              const noteDraft = noteDrafts[report.id] ?? "";
              const isUpdating = updatingId === report.id;
              return (
                <article
                  key={report.id}
                  id={`moderation-report-${report.id}`}
                  className="border-border bg-background/50 rounded-2xl border p-4 sm:p-5"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="text-foreground font-semibold capitalize">
                        {report.reason.replaceAll("_", " ")}
                      </h2>
                      <p className="text-muted-foreground mt-1 text-xs">
                        Collection:{" "}
                        <span className="text-foreground/80">
                          {report.collection_name || "Unavailable"}
                        </span>
                      </p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        Submitted {new Date(report.created_at).toLocaleString()}
                      </p>
                    </div>
                    <span className="border-border bg-surface-1 text-foreground rounded-lg border px-2.5 py-1 text-xs font-bold capitalize">
                      {report.status.replaceAll("_", " ")}
                    </span>
                  </div>

                  <dl className="text-muted-foreground mt-4 grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-3">
                    <div>
                      <dt className="font-semibold">Report ID</dt>
                      <dd className="text-foreground/80 break-all">{report.id}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold">Reported by</dt>
                      <dd className="text-foreground/80 break-all">{report.reporter_user_id}</dd>
                    </div>
                    {report.reported_user_id && (
                      <div>
                        <dt className="font-semibold">Reported member</dt>
                        <dd className="text-foreground/80 break-all">{report.reported_user_id}</dd>
                      </div>
                    )}
                    {report.message_id && (
                      <div>
                        <dt className="font-semibold">Message reference</dt>
                        <dd className="text-foreground/80 break-all">
                          {report.message_id}{" "}
                          <span className="text-muted-foreground">(message body not returned)</span>
                        </dd>
                      </div>
                    )}
                  </dl>

                  {report.details && (
                    <p className="text-foreground/85 border-border bg-background mt-4 rounded-xl border px-3 py-3 text-sm whitespace-pre-wrap">
                      {report.details}
                    </p>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    {report.status !== "reviewing" &&
                      report.status !== "resolved" &&
                      report.status !== "dismissed" && (
                        <button
                          type="button"
                          disabled={isUpdating}
                          onClick={() => void updateReport(report, "reviewing")}
                          className="rounded-xl border border-amber-500/40 px-3 py-2 text-xs font-semibold text-amber-800 disabled:opacity-50 dark:text-amber-200"
                        >
                          Mark reviewing
                        </button>
                      )}
                    {(report.status === "open" || report.status === "reviewing") && (
                      <button
                        type="button"
                        disabled={isUpdating}
                        onClick={() => void updateReport(report, "resolved")}
                        className="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                      >
                        Resolve
                      </button>
                    )}
                    {(report.status === "open" || report.status === "reviewing") && (
                      <button
                        type="button"
                        disabled={isUpdating}
                        onClick={() => void updateReport(report, "dismissed")}
                        className="border-border text-foreground rounded-xl border px-3 py-2 text-xs font-semibold disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                    )}
                    {(report.status === "resolved" || report.status === "dismissed") && (
                      <button
                        type="button"
                        disabled={isUpdating}
                        onClick={() => void updateReport(report, "open")}
                        className="border-primary/40 text-primary rounded-xl border px-3 py-2 text-xs font-semibold disabled:opacity-50"
                      >
                        Reopen
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleHistory(report.id)}
                      className="border-border text-foreground inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold"
                    >
                      <History size={14} /> Activity history{" "}
                      <ChevronDown
                        size={14}
                        className={`transition-transform ${expandedHistoryId === report.id ? "rotate-180" : ""}`}
                      />
                    </button>
                  </div>

                  <div className="mt-4 grid gap-2">
                    <label
                      htmlFor={`moderation-note-${report.id}`}
                      className="text-foreground text-xs font-semibold"
                    >
                      Internal moderator note
                    </label>
                    <textarea
                      id={`moderation-note-${report.id}`}
                      value={noteDraft}
                      maxLength={4000}
                      onChange={(event) =>
                        setNoteDrafts((current) => ({
                          ...current,
                          [report.id]: event.target.value,
                        }))
                      }
                      placeholder="Add an internal note for the moderation history…"
                      rows={2}
                      className="border-border bg-background text-foreground placeholder:text-muted-foreground/70 focus-visible:outline-primary w-full resize-y rounded-xl border px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2"
                    />
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-muted-foreground text-[11px]">
                        Visible only to workspace admins.
                      </span>
                      <button
                        type="button"
                        disabled={isUpdating || !noteDraft.trim()}
                        onClick={() => void updateReport(report, report.status, noteDraft)}
                        className="bg-primary text-primary-foreground rounded-xl px-3 py-2 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isUpdating ? "Saving…" : "Save note"}
                      </button>
                    </div>
                  </div>

                  {expandedHistoryId === report.id && (
                    <section
                      className="border-border mt-4 rounded-xl border p-3"
                      aria-label="Moderation action history"
                    >
                      <h3 className="text-foreground text-xs font-bold">Audit history</h3>
                      {history?.error && (
                        <p role="alert" className="text-destructive mt-2 text-xs">
                          {history.error}
                        </p>
                      )}
                      {history?.loading && (
                        <p role="status" className="text-muted-foreground mt-2 text-xs">
                          Loading history…
                        </p>
                      )}
                      {history?.items.map((action) => (
                        <div key={action.id} className="border-border mt-3 border-t pt-3 text-xs">
                          <div className="flex flex-wrap justify-between gap-2">
                            <span className="text-foreground font-semibold">
                              {formatAction(action)}
                            </span>
                            <time className="text-muted-foreground">
                              {new Date(action.created_at).toLocaleString()}
                            </time>
                          </div>
                          <p className="text-muted-foreground mt-1 break-all">
                            Actor: {action.actor_role}
                            {action.actor_user_id
                              ? ` · ${action.actor_user_id}`
                              : action.actor_role === "system"
                                ? ""
                                : " · account removed"}
                          </p>
                          {action.note && (
                            <p className="text-foreground/85 bg-background mt-2 rounded-lg px-3 py-2 whitespace-pre-wrap">
                              {action.note}
                            </p>
                          )}
                        </div>
                      ))}
                      {history &&
                        !history.loading &&
                        history.items.length === 0 &&
                        !history.error && (
                          <p className="text-muted-foreground mt-2 text-xs">
                            No activity recorded.
                          </p>
                        )}
                      {history?.hasMore && (
                        <button
                          type="button"
                          disabled={history.loading}
                          onClick={() => void loadHistory(report.id, true)}
                          className="border-border text-foreground mt-3 w-full rounded-xl border px-3 py-2 text-xs font-semibold disabled:opacity-50"
                        >
                          Load older activity
                        </button>
                      )}
                    </section>
                  )}
                </article>
              );
            })}
          </div>
        )}

        <div className="border-border mt-5 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <p className="text-muted-foreground text-xs" aria-live="polite">
            {total === 0
              ? "No reports"
              : `Showing ${offset + 1}–${Math.min(offset + reports.length, total)} of ${total}`}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={loading || offset === 0}
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
              className="border-border text-foreground inline-flex items-center gap-1 rounded-xl border px-3 py-2 text-xs font-semibold disabled:opacity-40"
            >
              <ChevronLeft size={14} />
              Previous
            </button>
            <button
              type="button"
              disabled={loading || !hasMore}
              onClick={() => setOffset((current) => current + PAGE_SIZE)}
              className="border-border text-foreground inline-flex items-center gap-1 rounded-xl border px-3 py-2 text-xs font-semibold disabled:opacity-40"
            >
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
