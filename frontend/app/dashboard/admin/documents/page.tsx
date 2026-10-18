"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileStack, Loader2, RefreshCcw, ShieldCheck } from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

interface TenantDocumentSummary {
  tenant_id: string;
  quarantined_count: number;
  error_count: number;
}

interface SummaryResponse {
  items: TenantDocumentSummary[];
}

interface RecoveryItem {
  job_id: string;
  status: string;
  checkpoint_stage?: string | null;
  resume_count: number;
  last_error_code?: string | null;
  updated_at?: string;
}

export default function AdminDocumentsPage() {
  const [items, setItems] = useState<TenantDocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [recovery, setRecovery] = useState<RecoveryItem[]>([]);

  const totals = useMemo(
    () =>
      items.reduce(
        (acc, item) => ({
          quarantined: acc.quarantined + item.quarantined_count,
          errors: acc.errors + item.error_count,
        }),
        { quarantined: 0, errors: 0 },
      ),
    [items],
  );

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = (await fetchWithAuth("/admin/documents/summary")) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load document summary (${res.status})`);
      }
      const data = (await res.json()) as SummaryResponse;
      setItems(Array.isArray(data.items) ? data.items : []);
      const recoveryRes = (await fetchWithAuth(
        "/admin/documents/recovery-history?limit=50",
      )) as Response;
      if (recoveryRes.ok) {
        const recoveryData = (await recoveryRes.json()) as { items?: RecoveryItem[] };
        setRecovery(Array.isArray(recoveryData.items) ? recoveryData.items : []);
      }
      setLastUpdated(new Date());
    } catch (err) {
      console.error(err);
      setError("Failed to load admin document summary.");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadSummary());
  }, [loadSummary]);

  return (
    <div className="space-y-6">
      <DashboardSectionHeader
        title="Document Processing Health"
        subtitle="Restricted Operations · Issue Counts Only"
        icon={ShieldCheck}
        accentClassName="bg-emerald-500 text-emerald-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(16,185,129,0.35)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
        actions={
          <button
            type="button"
            onClick={loadSummary}
            disabled={loading}
            className="bg-muted border-glass-border text-muted-foreground hover:text-foreground flex items-center gap-2 rounded-xl border p-2.5 text-sm font-bold transition-all"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCcw size={16} />}
            Refresh
          </button>
        }
      />

      {error ? (
        <div className="rounded-[1.35rem] border border-red-400/24 bg-red-400/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <p className="text-muted-foreground max-w-3xl text-sm leading-6">
        This restricted operations view shows issue counts and recovery status for triage. It does
        not expose filenames, document IDs, storage paths, or raw error messages.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        {[
          ["Quarantined", totals.quarantined.toLocaleString()],
          ["Errors", totals.errors.toLocaleString()],
        ].map(([label, value]) => (
          <div key={label} className="theme-panel rounded-[1.25rem] p-5">
            <p className="text-muted-foreground text-xs font-bold tracking-[0.16em] uppercase">
              {label}
            </p>
            <p className="text-foreground mt-2 text-3xl font-black">{value}</p>
          </div>
        ))}
      </div>

      <section className="theme-panel rounded-[1.5rem] p-5">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileStack size={18} className="text-emerald-400" />
            <h2 className="text-foreground text-sm font-bold tracking-[0.18em] uppercase">
              Workspace Processing Health
            </h2>
          </div>
          <span className="text-muted-foreground text-xs">
            {lastUpdated ? `Page refreshed ${lastUpdated.toLocaleTimeString()}` : "Not loaded"}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead className="text-muted-foreground border-glass-border border-b text-xs tracking-[0.14em] uppercase">
              <tr>
                <th className="py-3 pr-4">Workspace reference</th>
                <th className="py-3 pr-4">Quarantined</th>
                <th className="py-3 pr-4">Processing errors</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.tenant_id} className="border-glass-border border-b last:border-b-0">
                  <td className="text-foreground py-4 pr-4 font-mono text-xs">{item.tenant_id}</td>
                  <td className="py-4 pr-4">{item.quarantined_count.toLocaleString()}</td>
                  <td className="py-4 pr-4">{item.error_count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="theme-panel rounded-[1.5rem] p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-foreground text-sm font-bold tracking-[0.18em] uppercase">
              Recovery history
            </h2>
            <p className="text-muted-foreground mt-1 text-xs">
              Checkpoint stage and error codes for this workspace; document identifiers and raw
              failure text are hidden.
            </p>
          </div>
          <span className="text-muted-foreground text-xs">{recovery.length} records</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-muted-foreground border-glass-border border-b text-xs uppercase">
              <tr>
                <th className="py-3 pr-4">Stage</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">Resumes</th>
                <th className="py-3 pr-4">Error code</th>
              </tr>
            </thead>
            <tbody>
              {recovery.map((item) => (
                <tr key={item.job_id} className="border-glass-border border-b last:border-b-0">
                  <td className="py-3 pr-4">{item.checkpoint_stage ?? "—"}</td>
                  <td className="py-3 pr-4">{item.status}</td>
                  <td className="py-3 pr-4">{item.resume_count}</td>
                  <td className="text-muted-foreground max-w-[320px] truncate py-3 pr-4">
                    {item.last_error_code || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!recovery.length ? (
            <p className="text-muted-foreground py-6 text-center text-sm">
              No recovery events recorded.
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
