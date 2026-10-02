"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Crown,
  HardDrive,
  Loader2,
  ShieldCheck,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { useAuth } from "@/app/context/AuthContext";
import { fetchWithAuth } from "@/lib/api";
import { hasAdminRole } from "@/lib/roles";

type PlanCard = {
  id: string;
  name: string;
  storage_limit_bytes: number;
  description: string;
  features: string[];
  admin_only: boolean;
};

type PlansResponse = {
  current_plan: {
    id: string;
    name: string;
    storage_limit_bytes: number;
    description: string;
    admin_account: boolean;
  };
  usage: {
    documents_bytes: number;
    library_bytes: number;
    artifacts_bytes: number;
    pending_upload_bytes: number;
    account_data_bytes?: number;
    total_bytes: number;
  };
  plans: PlanCard[];
  storage_scope: string;
  beta?: {
    enabled: boolean;
    plan_id: string;
    plan_name: string;
    resurface_hours: number;
  };
};

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(0, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 1024 * 1024 * 10 ? 0 : 1)} MB`;
}

function formatLimit(bytes: number): string {
  const gigabyte = 1024 * 1024 * 1024;
  if (bytes >= gigabyte && bytes % gigabyte === 0) {
    return `${bytes / gigabyte} GB`;
  }
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

export default function PlanPage() {
  const { user } = useAuth();
  const isAdmin = hasAdminRole(user?.roles);
  const [data, setData] = useState<PlansResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = (await fetchWithAuth("/plans/current")) as Response;
        if (!response.ok) throw new Error("Unable to load plan information.");
        const payload = (await response.json()) as PlansResponse;
        if (!cancelled) setData(payload);
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Unable to load plan information.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const usagePercent = useMemo(() => {
    if (!data || data.current_plan.storage_limit_bytes <= 0) return 0;
    return Math.min(
      100,
      (data.usage.total_bytes / data.current_plan.storage_limit_bytes) * 100,
    );
  }, [data]);

  return (
    <div className="w-full space-y-8">
      <DashboardSectionHeader
        title="Plan & Storage"
        subtitle="Your account plan and tenant-isolated workspace storage"
        icon={HardDrive}
        accentClassName="bg-primary text-primary"
        accentGlowClassName="shadow-[0_0_20px_rgba(var(--primary),0.35)]"
      />

      <Link
        href="/dashboard/settings"
        className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft size={16} /> Back to Settings
      </Link>

      {loading && (
        <div className="settings-featured flex items-center gap-3 p-7 text-sm text-muted-foreground">
          <Loader2 className="animate-spin" size={18} /> Loading plan and storage information…
        </div>
      )}

      {error && (
        <div className="settings-featured flex items-center gap-3 p-7 text-sm text-destructive">
          <AlertCircle size={18} /> {error}
        </div>
      )}

      {data && (
        <>
          <section className="settings-featured overflow-hidden p-7">
            <div className="relative z-[1] grid gap-7 lg:grid-cols-[1fr_1.2fr] lg:items-center">
              <div>
                <div className="mb-3 flex items-center gap-2 text-xs font-bold tracking-[0.2em] text-primary uppercase">
                  <ShieldCheck size={15} /> Current plan
                </div>
                <h2 className="text-3xl font-black tracking-tight text-foreground">
                  {data.current_plan.name}
                </h2>
                <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
                  {data.current_plan.description} Your storage is isolated to this authenticated
                  tenant/workspace.
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/45 p-5">
                <div className="mb-3 flex items-center justify-between text-sm font-semibold">
                  <span>Storage used</span>
                  <span className="text-muted-foreground">
                    {formatBytes(data.usage.total_bytes)} / {formatLimit(data.current_plan.storage_limit_bytes)}
                  </span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-muted/60">
                  <div
                    className={`h-full rounded-full transition-all ${usagePercent >= 90 ? "bg-destructive" : "bg-primary"}`}
                    style={{ width: `${usagePercent}%` }}
                  />
                </div>
                <p className="mt-3 text-xs text-muted-foreground">{data.storage_scope}</p>
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-muted-foreground sm:grid-cols-4">
                  <span>Documents: {formatBytes(data.usage.documents_bytes)}</span>
                  <span>Library: {formatBytes(data.usage.library_bytes)}</span>
                  <span>Artifacts: {formatBytes(data.usage.artifacts_bytes)}</span>
                  <span>Uploads: {formatBytes(data.usage.pending_upload_bytes)}</span>
                  <span>Account data: {formatBytes(data.usage.account_data_bytes ?? 0)}</span>
                </div>
              </div>
            </div>
          </section>

          {data.beta?.enabled && (
            <section
              aria-label="Beta notice"
              className="settings-featured flex flex-col gap-2 p-6 sm:flex-row sm:items-center sm:gap-4"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-foreground">
                  You&apos;re assigned to {data.beta.plan_name} — free until production release
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Everything in AverQel is open during beta. Paid subscriptions arrive with the
                  production release; your workspace carries over unchanged.
                </p>
              </div>
              <span className="shrink-0 rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">
                Beta · Free
              </span>
            </section>
          )}

          <section>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-black tracking-tight text-foreground">Available plans</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Plan access is currently determined by your authenticated account role.
                </p>
              </div>
              {isAdmin && <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">Admin account</span>}
            </div>
            <div className="grid gap-5 lg:grid-cols-3">
              {data.plans.filter((plan) => !plan.admin_only || isAdmin).map((plan) => {
                const current = plan.id === data.current_plan.id;
                return (
                  <article
                    key={plan.id}
                    className={`relative flex h-full flex-col rounded-2xl border p-6 transition-all ${
                      current
                        ? "border-primary/50 bg-primary/[0.06] shadow-[0_0_32px_-12px_rgba(var(--primary),0.45)]"
                        : "border-border/70 bg-card/40"
                    }`}
                  >
                    {current && (
                      <span className="absolute top-4 right-4 rounded-full bg-primary px-2.5 py-1 text-[10px] font-black tracking-[0.12em] text-primary-foreground uppercase">
                        Current
                      </span>
                    )}
                    <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
                      {plan.id === "admin" ? <Crown size={21} /> : <HardDrive size={21} />}
                    </div>
                    <h3 className="text-xl font-black text-foreground">{plan.name}</h3>
                    <p className="mt-2 min-h-12 text-sm leading-6 text-muted-foreground">{plan.description}</p>
                    <div className="mt-5 flex items-end gap-2">
                      <span className="text-3xl font-black text-foreground">{formatLimit(plan.storage_limit_bytes)}</span>
                      <span className="pb-1 text-xs text-muted-foreground">storage</span>
                    </div>
                    <ul className="mt-6 space-y-3 border-t border-border/60 pt-5">
                      {plan.features.map((feature) => (
                        <li key={feature} className="flex gap-2 text-sm text-muted-foreground">
                          <CheckCircle2 className="mt-0.5 shrink-0 text-primary" size={16} />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
