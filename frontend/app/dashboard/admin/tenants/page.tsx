"use client";

import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Building2, Database, FileText, Loader2, Search, Users } from "lucide-react";
import toast from "react-hot-toast";

import { fetchWithAuth } from "@/lib/api";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

interface TenantStats {
  users_count: number;
  active_users_count: number;
  documents_count: number;
  queries_count: number;
  collections_count: number;
}

interface TenantSummary {
  tenant_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  status?: "active" | "empty" | "suspended" | "pending_deletion";
  last_activity_at?: string | null;
  stats: TenantStats;
}

interface TenantListResponse {
  items: TenantSummary[];
}

const formatDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

export default function AdminTenantsPage() {
  const [items, setItems] = useState<TenantSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const totals = items.reduce(
    (acc, tenant) => {
      acc.workspaces += 1;
      acc.users += tenant.stats.users_count;
      acc.documents += tenant.stats.documents_count;
      acc.collections += tenant.stats.collections_count;
      return acc;
    },
    { workspaces: 0, users: 0, documents: 0, collections: 0 },
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = (await fetchWithAuth("/admin/tenants")) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load tenants (${res.status})`);
      }
      const data = (await res.json()) as Partial<TenantListResponse>;
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch (error) {
      console.error(error);
      toast.error("Failed to load platform workspaces.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <DashboardSectionHeader
        title="Workspace Control"
        subtitle="Cross-Tenant Workspace Visibility"
        icon={Building2}
        accentClassName="bg-blue-500 text-blue-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(59,130,246,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
        actions={
          <button
            type="button"
            onClick={() => void load()}
            className="theme-chip rounded-full px-4 py-2 text-xs font-semibold tracking-[0.18em] uppercase"
          >
            Refresh
          </button>
        }
      />

      {loading ? (
        <div className="text-muted-foreground flex items-center gap-3 rounded-2xl px-4 py-8 text-sm">
          <Loader2 size={16} className="animate-spin" />
          Loading workspaces...
        </div>
      ) : items.length === 0 ? (
        <div className="theme-panel-muted text-muted-foreground rounded-[1.4rem] px-4 py-8 text-center text-sm">
          No workspaces found.
        </div>
      ) : (
        <>
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_22rem]">
            <div className="theme-panel overflow-hidden rounded-[1.6rem] p-6">
              <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_15rem] 2xl:items-start">
                <div className="max-w-2xl min-w-0 space-y-3">
                  <div className="theme-pill border-primary/20 bg-primary/5 text-primary">
                    <Building2 size={12} />
                    Platform Workspace Map
                  </div>
                  <div>
                    <h2 className="text-foreground text-2xl font-semibold tracking-tight">
                      Cross-tenant visibility without opening tenant content
                    </h2>
                    <p className="text-muted-foreground mt-2 text-sm leading-7">
                      Review live workspace footprint, operational density, and tenant-level
                      activity shape from one compact owner surface.
                    </p>
                  </div>
                </div>

                <div className="grid min-w-0 grid-cols-2 gap-3">
                  <SummaryCell label="Workspaces" value={totals.workspaces} tone="primary" />
                  <SummaryCell label="Users" value={totals.users} tone="primary" />
                  <SummaryCell label="Documents" value={totals.documents} tone="amber" />
                  <SummaryCell label="Collections" value={totals.collections} tone="primary" />
                </div>
              </div>
            </div>

            <div className="theme-panel rounded-[1.6rem] p-6">
              <div className="text-primary flex items-center gap-2 text-[11px] font-black tracking-[0.2em] uppercase">
                <Database size={14} className="text-primary" />
                Control Notes
              </div>
              <div className="mt-5 space-y-4">
                <div className="rounded-[1.15rem] border border-white/6 bg-white/[0.02] p-4">
                  <p className="text-foreground text-sm font-semibold">Metadata-only surface</p>
                  <p className="text-muted-foreground mt-2 text-sm leading-6">
                    This page is for tenant footprint and operational review, not direct document
                    inspection.
                  </p>
                </div>
                <div className="rounded-[1.15rem] border border-white/6 bg-white/[0.02] p-4">
                  <p className="text-foreground text-sm font-semibold">Fast comparison</p>
                  <p className="text-muted-foreground mt-2 text-sm leading-6">
                    Density cards are tuned for scanning many workspaces quickly instead of reading
                    oversized blocks one by one.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            {items.map((tenant) => (
              <section
                key={tenant.tenant_id}
                className="theme-panel flex min-h-[23rem] flex-col rounded-[1.5rem] p-5"
              >
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_10.5rem]">
                  <div className="min-w-0">
                    <div className="theme-accent-pill flex h-11 w-11 items-center justify-center rounded-[1rem]">
                      <Building2 size={18} />
                    </div>
                    <h2 className="text-foreground mt-4 [display:-webkit-box] max-w-[20ch] overflow-hidden text-xl leading-tight font-semibold [-webkit-box-orient:vertical] [-webkit-line-clamp:2]">
                      {tenant.name}
                    </h2>
                    <p className="text-muted-foreground mt-2 max-w-full font-mono text-[11px] leading-5 break-all">
                      {tenant.tenant_id}
                    </p>
                  </div>
                  <div className="space-y-2 xl:text-right">
                    <div className="theme-chip justify-center rounded-full px-3 py-1 text-[10px] font-bold tracking-[0.18em] uppercase xl:ml-auto xl:w-fit">
                      {tenant.status ?? "active"} · Updated {formatDate(tenant.updated_at)}
                    </div>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
                  <MetricTile
                    icon={<Users className="text-primary" size={16} />}
                    label="Users"
                    value={tenant.stats.users_count}
                  />
                  <MetricTile
                    icon={<Users className="text-primary" size={16} />}
                    label="Active"
                    value={tenant.stats.active_users_count}
                  />
                  <MetricTile
                    icon={<FileText className="text-amber-300" size={16} />}
                    label="Documents"
                    value={tenant.stats.documents_count}
                  />
                  <MetricTile
                    icon={<Search className="text-primary" size={16} />}
                    label="Queries"
                    value={tenant.stats.queries_count}
                  />
                  <MetricTile
                    icon={<Database className="text-primary" size={16} />}
                    label="Collections"
                    value={tenant.stats.collections_count}
                  />
                </div>

                <div className="mt-5 flex flex-1 flex-col justify-end">
                  <div className="border-glass-border rounded-[1.1rem] border border-dashed bg-white/[0.02] px-4 py-3">
                    <p className="text-muted-foreground text-[11px] leading-6">
                      Owner-level visibility only. This card exposes footprint and usage density
                      without opening tenant documents, chats, or private content bodies.
                    </p>
                  </div>
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function SummaryCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "primary" | "emerald" | "amber" | "violet";
}) {
  const toneClass =
    tone === "primary"
      ? "text-primary border-primary/15 bg-primary/[0.06]"
      : tone === "emerald"
        ? "text-emerald-500 border-emerald-500/15 bg-emerald-500/[0.06]"
        : tone === "amber"
          ? "text-amber-500 border-amber-500/15 bg-amber-500/[0.06]"
          : "text-primary border-primary/15 bg-primary/[0.06]";

  return (
    <div className={`min-w-0 rounded-[1.1rem] border px-4 py-3 ${toneClass}`}>
      <p className="truncate text-[10px] font-bold tracking-[0.18em] uppercase opacity-75">
        {label}
      </p>
      <p className="mt-3 text-3xl leading-none font-semibold">{value}</p>
    </div>
  );
}

function MetricTile({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="theme-panel-muted flex min-h-[7.5rem] min-w-0 flex-col rounded-[1rem] p-4">
      <div>{icon}</div>
      <p className="text-muted-foreground mt-3 truncate text-[10px] font-bold tracking-[0.18em] uppercase">
        {label}
      </p>
      <p className="text-foreground mt-auto text-3xl leading-none font-semibold">{value}</p>
    </div>
  );
}
