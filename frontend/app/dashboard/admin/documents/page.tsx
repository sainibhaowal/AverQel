"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { FileStack, Loader2, RefreshCcw, ShieldCheck } from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";

interface StatusCount {
  status: string;
  count: number;
}

interface TenantDocumentSummary {
  tenant_id: string;
  documents_count: number;
  storage_bytes: number;
  quarantined_count: number;
  status_counts: StatusCount[];
  error_count: number;
}

interface SummaryResponse {
  items: TenantDocumentSummary[];
}

const formatStorage = (bytes: number) => {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

export default function AdminDocumentsPage() {
  const [items, setItems] = useState<TenantDocumentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const totals = useMemo(
    () =>
      items.reduce(
        (acc, item) => ({
          documents: acc.documents + item.documents_count,
          storage: acc.storage + item.storage_bytes,
          quarantined: acc.quarantined + item.quarantined_count,
          errors: acc.errors + item.error_count,
        }),
        { documents: 0, storage: 0, quarantined: 0, errors: 0 },
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
        title="Document Privacy"
        subtitle="Metadata-Only Platform Oversight"
        icon={ShieldCheck}
        accentClassName="bg-blue-500 text-blue-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(59,130,246,0.4)]"
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

      <div className="grid gap-4 md:grid-cols-4">
        {[
          ["Documents", totals.documents.toLocaleString()],
          ["Storage", formatStorage(totals.storage)],
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
              Tenant Metadata
            </h2>
          </div>
          <span className="text-muted-foreground text-xs">
            {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Not loaded"}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-muted-foreground border-glass-border border-b text-xs tracking-[0.14em] uppercase">
              <tr>
                <th className="py-3 pr-4">Tenant</th>
                <th className="py-3 pr-4">Documents</th>
                <th className="py-3 pr-4">Storage</th>
                <th className="py-3 pr-4">Quarantined</th>
                <th className="py-3 pr-4">Errors</th>
                <th className="py-3 pr-4">Statuses</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.tenant_id} className="border-glass-border border-b last:border-b-0">
                  <td className="text-foreground py-4 pr-4 font-mono text-xs">{item.tenant_id}</td>
                  <td className="py-4 pr-4">{item.documents_count.toLocaleString()}</td>
                  <td className="py-4 pr-4">{formatStorage(item.storage_bytes)}</td>
                  <td className="py-4 pr-4">{item.quarantined_count.toLocaleString()}</td>
                  <td className="py-4 pr-4">{item.error_count.toLocaleString()}</td>
                  <td className="py-4 pr-4">
                    <div className="flex flex-wrap gap-2">
                      {item.status_counts.map((status) => (
                        <span
                          key={`${item.tenant_id}:${status.status}`}
                          className="bg-muted text-muted-foreground rounded-md px-2 py-1 text-xs font-semibold"
                        >
                          {status.status}: {status.count}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
