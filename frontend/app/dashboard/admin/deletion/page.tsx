"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle,
  Trash2,
  Clock,
  CheckCircle2,
  XCircle,
  RefreshCcw,
  Loader2,
  ChevronRight,
  Info,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Check,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { fetchWithAuth } from "@/lib/api";
import { hasAdminRole } from "@/lib/roles";
import toast from "react-hot-toast";
import { useAuth } from "@/app/context/AuthContext";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

interface DeletionRequest {
  deletion_id: string;
  tenant_id: string;
  status: string;
  scope: string;
  reason: string | null;
  can_approve: boolean;
  error_code: string | null;
  error_message: string | null;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
}

interface DeletionListResponse {
  items: DeletionRequest[];
}

interface TenantSummary {
  tenant_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  seats_used: number;
}

interface TenantListResponse {
  items: TenantSummary[];
}

interface WorkspaceMenuPosition {
  top: number;
  left: number;
  width: number;
}

interface FloatingTooltipPosition {
  top: number;
  left: number;
}

export default function DeletionPage() {
  const { user } = useAuth();
  const isAdmin = hasAdminRole(user?.roles);
  const [requests, setRequests] = useState<DeletionRequest[]>([]);
  const [tenants, setTenants] = useState<TenantSummary[]>([]);
  const [loadingTenants, setLoadingTenants] = useState(false);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(user?.tenant_id ?? null);
  const [expandedRequestIds, setExpandedRequestIds] = useState<string[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [reason, setReason] = useState<"workspace_offboarding" | "security_incident">(
    "workspace_offboarding",
  );
  const [targetConfirmation, setTargetConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [approvingRequestId, setApprovingRequestId] = useState<string | null>(null);
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const workspaceMenuRef = useRef<HTMLDivElement | null>(null);
  const workspaceTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [workspaceMenuPosition, setWorkspaceMenuPosition] = useState<WorkspaceMenuPosition | null>(
    null,
  );
  const controlTooltipTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [controlTooltipVisible, setControlTooltipVisible] = useState(false);
  const [controlTooltipPosition, setControlTooltipPosition] =
    useState<FloatingTooltipPosition | null>(null);

  const hasActiveRequests = useMemo(
    () =>
      requests.some((request) =>
        ["awaiting_approval", "queued", "processing"].includes(request.status),
      ),
    [requests],
  );
  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.tenant_id === selectedTenantId) ?? null,
    [selectedTenantId, tenants],
  );
  const targetLabel = selectedTenant?.name ?? "Current Workspace";
  const deletionHistoryQuery = useMemo(() => {
    const params = new URLSearchParams({ limit: "20" });
    if (isAdmin && selectedTenantId) {
      params.set("target_tenant_id", selectedTenantId);
    }
    return params.toString();
  }, [isAdmin, selectedTenantId]);

  const fetchTenants = useCallback(async () => {
    if (!isAdmin) return;
    setLoadingTenants(true);
    try {
      const res = (await fetchWithAuth("/admin/tenants")) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load workspaces (${res.status})`);
      }
      const data = (await res.json()) as TenantListResponse;
      const items = Array.isArray(data.items) ? data.items : [];
      setTenants(items);
      setSelectedTenantId((current) => current ?? items[0]?.tenant_id ?? null);
    } catch (error) {
      console.error("Failed to load workspaces", error);
      toast.error("Failed to load workspaces.");
    } finally {
      setLoadingTenants(false);
    }
  }, [isAdmin]);

  const fetchRequests = useCallback(async () => {
    setLoadingRequests(true);
    try {
      const res = (await fetchWithAuth(
        `/admin/data-deletions?${deletionHistoryQuery}`,
      )) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load deletion requests (${res.status})`);
      }
      const data = (await res.json()) as DeletionListResponse;
      setRequests(
        data.items.map((item) => ({
          deletion_id: item.deletion_id,
          tenant_id: item.tenant_id,
          status: item.status,
          scope: item.scope,
          reason: item.reason,
          can_approve: item.can_approve,
          error_code: item.error_code,
          error_message: item.error_message,
          requested_at: item.requested_at,
          started_at: item.started_at,
          completed_at: item.completed_at,
          failed_at: item.failed_at,
        })),
      );
    } catch (error) {
      console.error("Failed to load deletion requests", error);
      toast.error("Failed to load deletion history.");
    } finally {
      setLoadingRequests(false);
    }
  }, [deletionHistoryQuery]);

  useEffect(() => {
    if (isAdmin) {
      queueMicrotask(() => void fetchTenants());
    }
  }, [fetchTenants, isAdmin]);

  useEffect(() => {
    if (isAdmin && !selectedTenantId) return;
    queueMicrotask(() => void fetchRequests());
  }, [fetchRequests, isAdmin, selectedTenantId]);

  useEffect(() => {
    if (!hasActiveRequests) {
      return;
    }
    const interval = window.setInterval(() => {
      void fetchRequests();
    }, 4000);
    return () => window.clearInterval(interval);
  }, [fetchRequests, hasActiveRequests]);

  useEffect(() => {
    if (!workspaceMenuOpen) return;

    const updateWorkspaceMenuPosition = () => {
      const trigger = workspaceTriggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      setWorkspaceMenuPosition({
        top: rect.bottom + 8,
        left: rect.left,
        width: rect.width,
      });
    };

    updateWorkspaceMenuPosition();

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        workspaceMenuRef.current &&
        !workspaceMenuRef.current.contains(target) &&
        !workspaceTriggerRef.current?.contains(target)
      ) {
        setWorkspaceMenuOpen(false);
      }
    };

    window.addEventListener("resize", updateWorkspaceMenuPosition);
    window.addEventListener("scroll", updateWorkspaceMenuPosition, true);
    window.addEventListener("mousedown", handlePointerDown);
    return () => {
      window.removeEventListener("resize", updateWorkspaceMenuPosition);
      window.removeEventListener("scroll", updateWorkspaceMenuPosition, true);
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, [workspaceMenuOpen]);

  useEffect(() => {
    if (!controlTooltipVisible) return;

    const updateControlTooltipPosition = () => {
      const trigger = controlTooltipTriggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      setControlTooltipPosition({
        top: rect.top - 10,
        left: rect.right,
      });
    };

    updateControlTooltipPosition();

    window.addEventListener("resize", updateControlTooltipPosition);
    window.addEventListener("scroll", updateControlTooltipPosition, true);
    return () => {
      window.removeEventListener("resize", updateControlTooltipPosition);
      window.removeEventListener("scroll", updateControlTooltipPosition, true);
    };
  }, [controlTooltipVisible]);

  const handleWipe = async () => {
    if (isAdmin && !selectedTenantId) {
      toast.error("Select a workspace first.");
      return;
    }
    const targetTenantId = selectedTenantId ?? user?.tenant_id ?? null;
    const expectedConfirmation = targetTenantId ? `DELETE ${targetTenantId}` : "";
    if (!targetTenantId || targetConfirmation.trim() !== expectedConfirmation) return;
    setSubmitting(true);
    try {
      const res = (await fetchWithAuth("/admin/data-deletions", {
        method: "POST",
        body: JSON.stringify({
          reason,
          target_confirmation: targetConfirmation.trim(),
          ...(isAdmin && selectedTenantId ? { target_tenant_id: selectedTenantId } : {}),
        }),
      })) as Response;
      if (res.ok) {
        const data = await res.json();
        setShowModal(false);
        setReason("workspace_offboarding");
        setTargetConfirmation("");
        toast.success(
          `Deletion request is waiting for a second administrator: ${data.deletion_id}`,
        );
        await fetchRequests();
      } else {
        const errorData = await res.json().catch(() => null);
        toast.error(
          errorData?.error?.message || errorData?.message || "Failed to initiate data deletion.",
        );
        await fetchRequests();
      }
    } catch (e) {
      console.error("Deletion failed", e);
      toast.error("An unexpected error occurred.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleApprove = async (request: DeletionRequest) => {
    const confirmed = window.confirm(
      `Approve the irreversible workspace data deletion for ${request.tenant_id}? This approval will be recorded and the deletion will start. Account records, support, feedback, and audit records are retained.`,
    );
    if (!confirmed) return;
    setApprovingRequestId(request.deletion_id);
    try {
      const query = new URLSearchParams({ target_tenant_id: request.tenant_id });
      const response = (await fetchWithAuth(
        `/admin/data-deletions/${request.deletion_id}/approve?${query.toString()}`,
        { method: "POST" },
      )) as Response;
      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        toast.error(errorData?.error?.message || "Could not approve this deletion request.");
        return;
      }
      toast.success("Deletion approved and queued.");
      await fetchRequests();
    } catch (error) {
      console.error("Deletion approval failed", error);
      toast.error("Could not approve this deletion request.");
    } finally {
      setApprovingRequestId(null);
    }
  };

  const closeConfirmation = () => {
    setShowModal(false);
    setTargetConfirmation("");
  };

  const toggleExpanded = (deletionId: string) => {
    setExpandedRequestIds((current) =>
      current.includes(deletionId)
        ? current.filter((item) => item !== deletionId)
        : [...current, deletionId],
    );
  };

  const formatTimestamp = (value: string | null) => {
    if (!value) return "Not recorded";
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 size={16} className="text-green-500" />;
      case "failed":
        return <XCircle size={16} className="text-red-500" />;
      case "processing":
      case "in_progress":
        return <Loader2 size={16} className="text-primary animate-spin" />;
      case "queued":
        return <Clock size={16} className="text-amber-400" />;
      default:
        return <Clock size={16} className="text-slate-500" />;
    }
  };

  return (
    <div className="dashboard-theme-scope w-full space-y-8">
      <DashboardSectionHeader
        title="Data Deletion"
        subtitle="Permanent Workspace Data Removal"
        icon={Trash2}
        accentClassName="bg-red-500 text-red-400"
        accentGlowClassName="shadow-[0_0_18px_rgba(239,68,68,0.28)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
      />

      <div className="relative z-[40] grid grid-cols-1 gap-5">
        <div
          className="glass-card relative z-[40] flex flex-col space-y-5 p-6"
          style={{ overflow: "visible" }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-foreground text-xs font-bold tracking-widest uppercase">
                Deletion Target
              </h2>
              <p className="text-muted-foreground mt-2 max-w-[56ch] text-sm leading-7">
                This operation removes content from one workspace. Account data-rights requests must
                be submitted through{" "}
                <a href="/dashboard/support" className="text-primary underline underline-offset-2">
                  support
                </a>
                ; this workspace purge does not process them.
              </p>
            </div>
            {isAdmin ? (
              <span className="theme-chip shrink-0 rounded-full px-3 py-1 text-[10px] font-bold tracking-[0.18em] uppercase">
                Admin Scope
              </span>
            ) : null}
          </div>

          {isAdmin ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem] xl:items-start">
              <div className="min-w-0">
                <label className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                  Workspace Selection
                </label>
                <div className="mt-2 min-w-0">
                  <button
                    ref={workspaceTriggerRef}
                    type="button"
                    onClick={() => {
                      if (!loadingTenants) setWorkspaceMenuOpen((current) => !current);
                    }}
                    disabled={loadingTenants}
                    className="theme-panel-muted border-glass-border text-foreground hover:border-primary/25 hover:bg-primary/5 flex h-12 w-full min-w-0 items-center justify-between rounded-xl border px-4 text-left text-sm transition-all outline-none disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span className="block min-w-0 flex-1 truncate pr-2">
                      {loadingTenants
                        ? "Loading workspaces..."
                        : selectedTenant?.name || "Select workspace"}
                    </span>
                    <ChevronDown
                      size={16}
                      className={`text-primary ml-3 shrink-0 transition-transform ${
                        workspaceMenuOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>
                </div>
              </div>
              <div className="theme-panel-muted flex min-h-[6.2rem] min-w-0 flex-col rounded-xl p-4">
                <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                  Workspace ID
                </p>
                <p className="text-foreground mt-2 max-w-full overflow-hidden font-mono text-xs leading-5 break-all">
                  {selectedTenant?.tenant_id ?? "No workspace selected"}
                </p>
              </div>
            </div>
          ) : (
            <div className="theme-panel-muted text-muted-foreground flex min-h-[6.2rem] items-center rounded-xl p-4 text-sm">
              This page applies only to your current workspace context.
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="theme-panel-muted flex min-h-[7rem] min-w-0 flex-col rounded-xl p-4">
              <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                Workspace
              </p>
              <p
                className="text-foreground mt-auto [display:-webkit-box] overflow-hidden text-sm leading-6 font-semibold break-words [-webkit-box-orient:vertical] [-webkit-line-clamp:2]"
                title={targetLabel}
              >
                {targetLabel}
              </p>
            </div>
            <div className="theme-panel-muted flex min-h-[7rem] flex-col rounded-xl p-4">
              <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                Seats in use
              </p>
              <p className="text-foreground mt-auto text-3xl leading-none font-semibold">
                {selectedTenant?.seats_used ?? "—"}
              </p>
            </div>
          </div>
        </div>
      </div>

      {typeof document !== "undefined" && workspaceMenuPosition
        ? createPortal(
            <AnimatePresence>
              {workspaceMenuOpen ? (
                <div
                  ref={workspaceMenuRef}
                  className="fixed z-[260]"
                  style={{
                    top: workspaceMenuPosition.top,
                    left: workspaceMenuPosition.left,
                    width: workspaceMenuPosition.width,
                  }}
                >
                  <motion.div
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.98 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                    className="theme-panel border-glass-border max-h-72 overflow-x-hidden overflow-y-auto rounded-2xl border p-2 shadow-[0_18px_60px_rgba(0,0,0,0.42)]"
                    style={{
                      overflowY: "auto",
                      overflowX: "hidden",
                      WebkitOverflowScrolling: "touch",
                    }}
                  >
                    {tenants.map((tenant) => {
                      const selected = tenant.tenant_id === selectedTenantId;
                      return (
                        <button
                          key={tenant.tenant_id}
                          type="button"
                          onClick={() => {
                            setSelectedTenantId(tenant.tenant_id);
                            setTargetConfirmation("");
                            setWorkspaceMenuOpen(false);
                          }}
                          className={`flex w-full min-w-0 items-center justify-between rounded-xl px-3 py-3 text-left text-sm transition-all ${
                            selected
                              ? "bg-primary/15 text-primary"
                              : "text-foreground/78 hover:bg-white/[0.04]"
                          }`}
                        >
                          <span className="block min-w-0 flex-1 truncate pr-2 font-semibold">
                            {tenant.name}
                          </span>
                          {selected ? (
                            <Check size={15} className="text-primary ml-3 shrink-0" />
                          ) : null}
                        </button>
                      );
                    })}
                  </motion.div>
                </div>
              ) : null}
            </AnimatePresence>,
            document.body,
          )
        : null}

      {typeof document !== "undefined" && controlTooltipVisible && controlTooltipPosition
        ? createPortal(
            <AnimatePresence>
              <motion.div
                initial={{ opacity: 0, y: 6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 4, scale: 0.98 }}
                transition={{ duration: 0.14, ease: "easeOut" }}
                className="pointer-events-none fixed z-[280] max-w-[min(28rem,calc(100vw-24px))] -translate-x-full -translate-y-full rounded-lg border border-white/12 bg-slate-950/96 px-3 py-2 text-xs leading-5 text-slate-100 shadow-[0_18px_50px_rgba(0,0,0,0.42)]"
                style={{
                  top: controlTooltipPosition.top,
                  left: controlTooltipPosition.left,
                }}
                role="tooltip"
              >
                This wipes only the selected workspace. It does not delete all users across the
                AverQel platform.
              </motion.div>
            </AnimatePresence>,
            document.body,
          )
        : null}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(22rem,1fr)] xl:items-start 2xl:grid-cols-[minmax(0,1.7fr)_minmax(24rem,1fr)]">
        <div className="space-y-6">
          <div className="flex min-h-[8.5rem] gap-4 rounded-2xl border border-red-500/20 bg-red-500/10 p-5">
            <AlertTriangle className="shrink-0 text-red-500" size={24} />
            <div>
              <h4 className="flex items-center gap-2 font-bold text-red-400">
                Atomic Wipe Protocol
                <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-bold tracking-tighter text-red-500 uppercase">
                  IRREVERSIBLE
                </span>
              </h4>
              <p className="mt-2 text-sm leading-relaxed text-red-500/70 italic">
                A request and approval from two different authorized administrators are required
                before this irreversible workspace purge starts. This removes workspace documents
                and source files, extracted text and embeddings, ingestion/index records, queries
                and citations, conversations and messages, Qel Connect collections and sharing,
                comments, and pinned findings. User accounts, provider settings, support and
                feedback records, and audit records remain. Account and data-rights requests use
                separate privacy controls. Any storage cleanup retries continue separately.
              </p>
            </div>
          </div>

          {/* Active Status Placeholder */}
          <div className="glass-card flex overflow-hidden lg:max-h-[34rem] lg:min-h-[34rem] lg:flex-col">
            <div className="border-glass-border bg-muted/30 flex items-center justify-between border-b px-6 py-4">
              <h3 className="text-foreground flex items-center gap-2 text-sm font-bold tracking-widest uppercase">
                <ShieldAlert size={14} className="text-primary" />
                Execution History
              </h3>
              <span className="text-muted-foreground hidden text-[10px] font-bold tracking-widest uppercase sm:inline">
                {targetLabel}
              </span>
              <button
                type="button"
                onClick={() => void fetchRequests()}
                disabled={loadingRequests}
                className="text-muted-foreground hover:text-foreground flex items-center gap-2 text-[10px] font-bold tracking-widest uppercase transition-colors disabled:opacity-60"
              >
                <RefreshCcw size={12} className={loadingRequests ? "animate-spin" : ""} /> Sync
                Status
              </button>
            </div>

            <div className="divide-glass-border divide-y lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
              {loadingRequests ? (
                <div className="flex items-center justify-center gap-3 p-12 text-center">
                  <Loader2 size={18} className="text-primary animate-spin" />
                  <p className="text-muted-foreground text-sm">Loading deletion history...</p>
                </div>
              ) : requests.length > 0 ? (
                requests.map((req) => {
                  const isExpanded = expandedRequestIds.includes(req.deletion_id);
                  return (
                    <div key={req.deletion_id} className="p-6">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-foreground text-sm font-bold tracking-widest break-all uppercase">
                            {req.deletion_id}
                          </p>
                          <p className="text-muted-foreground mt-1 text-xs">
                            Status:{" "}
                            {req.status === "awaiting_approval"
                              ? "Awaiting second approval"
                              : req.status}
                          </p>
                          <p className="text-muted-foreground mt-2 text-[11px]">
                            Requested: {formatTimestamp(req.requested_at)}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-3">
                          {getStatusIcon(req.status)}
                          {req.status === "awaiting_approval" && req.can_approve ? (
                            <button
                              type="button"
                              onClick={() => void handleApprove(req)}
                              disabled={approvingRequestId === req.deletion_id}
                              className="inline-flex items-center gap-2 rounded-full border border-amber-500/35 bg-amber-500/10 px-3 py-1.5 text-[10px] font-bold tracking-widest text-amber-600 uppercase transition-colors hover:bg-amber-500/20 disabled:opacity-60"
                            >
                              {approvingRequestId === req.deletion_id ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                <CheckCircle2 size={12} />
                              )}
                              Approve purge
                            </button>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => toggleExpanded(req.deletion_id)}
                            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-[10px] font-bold tracking-widest uppercase transition-colors"
                          >
                            {isExpanded ? "Hide Details" : "View Details"}
                            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                          </button>
                        </div>
                      </div>

                      <AnimatePresence initial={false}>
                        {isExpanded ? (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="mt-4 space-y-4 rounded-2xl border border-white/8 bg-white/[0.02] p-4">
                              <div className="grid gap-3 sm:grid-cols-2">
                                <div className="rounded-xl border border-white/6 bg-black/10 p-3">
                                  <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                                    Reason
                                  </p>
                                  <p className="text-foreground mt-2 text-sm">
                                    {req.reason?.trim() || "No reason provided"}
                                  </p>
                                </div>
                                <div className="rounded-xl border border-white/6 bg-black/10 p-3">
                                  <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                                    Scope
                                  </p>
                                  <p className="text-foreground mt-2 text-sm">{req.scope}</p>
                                </div>
                              </div>

                              <div className="grid gap-3 sm:grid-cols-3">
                                <div className="rounded-xl border border-white/6 bg-black/10 p-3">
                                  <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                                    Started
                                  </p>
                                  <p className="text-foreground mt-2 text-sm">
                                    {formatTimestamp(req.started_at)}
                                  </p>
                                </div>
                                <div className="rounded-xl border border-white/6 bg-black/10 p-3">
                                  <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                                    Completed
                                  </p>
                                  <p className="text-foreground mt-2 text-sm">
                                    {formatTimestamp(req.completed_at)}
                                  </p>
                                </div>
                                <div className="rounded-xl border border-white/6 bg-black/10 p-3">
                                  <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                                    Failed
                                  </p>
                                  <p className="text-foreground mt-2 text-sm">
                                    {formatTimestamp(req.failed_at)}
                                  </p>
                                </div>
                              </div>

                              {req.error_code || req.error_message ? (
                                <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3">
                                  <p className="text-[10px] font-bold tracking-widest text-red-400 uppercase">
                                    Failure Details
                                  </p>
                                  <p className="mt-2 text-sm text-red-200">
                                    {req.error_code || "Error"}
                                    {req.error_message ? `: ${req.error_message}` : ""}
                                  </p>
                                </div>
                              ) : null}
                            </div>
                          </motion.div>
                        ) : null}
                      </AnimatePresence>
                    </div>
                  );
                })
              ) : (
                <div className="flex h-full min-h-[18rem] flex-col items-center justify-center gap-4 p-12 text-center opacity-30">
                  <Trash2 size={48} className="text-muted-foreground" />
                  <div>
                    <p className="text-foreground text-sm font-bold tracking-widest uppercase">
                      No Active Wipes
                    </p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      Deletion history is purged after 30 days.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-6 xl:sticky xl:top-0">
          <div className="glass-card space-y-6 overflow-visible p-6">
            <div className="border-glass-border flex items-center gap-2 border-b pb-4">
              <h3 className="text-foreground text-xs font-bold tracking-widest uppercase">
                Control Zone
              </h3>
              <button
                type="button"
                ref={controlTooltipTriggerRef}
                onMouseEnter={() => setControlTooltipVisible(true)}
                onMouseLeave={() => setControlTooltipVisible(false)}
                onFocus={() => setControlTooltipVisible(true)}
                onBlur={() => setControlTooltipVisible(false)}
                className="theme-chip text-foreground/70 hover:text-foreground inline-flex h-7 w-7 items-center justify-center rounded-full"
                aria-label="Wipe scope information"
                title="This wipes only the selected workspace. It does not delete all users across the AverQel platform."
              >
                <Info size={13} />
              </button>
            </div>

            <div className="space-y-4">
              <div className="rounded-[1.1rem] border border-orange-500/10 bg-orange-500/5 p-4">
                <h4 className="mb-2 text-xs font-bold tracking-tight text-orange-400 uppercase">
                  Requirement Traceability
                </h4>
                <p className="text-[11px] leading-relaxed text-orange-400/70 italic">
                  Select the operational reason. You must also type the exact workspace ID to
                  confirm this irreversible request.
                </p>
              </div>

              <button
                onClick={() => setShowModal(true)}
                disabled={submitting}
                className="flex h-13 w-full items-center justify-center gap-2 rounded-[1.1rem] bg-red-600 px-4 text-sm font-bold tracking-widest text-white uppercase shadow-lg shadow-red-500/25 transition-all hover:bg-red-500 disabled:opacity-60"
              >
                <Trash2 size={18} />
                Execute Workspace Wipe
              </button>
            </div>
          </div>

          <div className="glass-card space-y-5 p-6">
            <h3 className="text-foreground mb-4 flex items-center gap-2 text-xs font-bold tracking-widest uppercase">
              <Info size={14} className="text-muted-foreground" />
              Scope of Deletion
            </h3>
            <ul className="space-y-3 text-[11px] font-medium text-slate-500">
              <li className="flex items-center gap-2">
                <ChevronRight size={10} className="text-primary" />
                Source files and derived artifacts; failed storage deletes enter a retry queue
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight size={10} className="text-primary" />
                Queries, chats, comments, and Qel Connect workspace data
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight size={10} className="text-primary" />
                User accounts, provider settings, support, and feedback remain
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight size={10} className="text-red-500" />
                <span className="font-bold text-slate-400">EXCLUDES:</span> Audit Trail Events
              </li>
            </ul>
            <div className="theme-panel-muted rounded-[1.1rem] p-4">
              <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                Current Target
              </p>
              <p className="text-foreground mt-2 text-sm font-semibold">{targetLabel}</p>
              {selectedTenant?.tenant_id ? (
                <p className="text-muted-foreground mt-2 font-mono text-xs break-all">
                  {selectedTenant.tenant_id}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      <AnimatePresence>
        {showModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={closeConfirmation}
              className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="glass-card relative w-full max-w-md space-y-8 overflow-hidden border-red-500/20 p-10 shadow-2xl"
            >
              <div className="pointer-events-none absolute top-0 right-0 p-8 opacity-10">
                <Trash2 size={120} className="text-red-500" />
              </div>

              <div className="space-y-2">
                <h3 className="text-foreground text-2xl font-bold">Confirm Removal</h3>
                <p className="text-muted-foreground text-sm italic">
                  Verification required to proceed with data destruction.
                </p>
              </div>

              <div className="space-y-4">
                <div className="theme-panel-muted rounded-xl p-4">
                  <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                    Target Workspace
                  </p>
                  <p className="text-foreground mt-2 text-sm font-semibold">{targetLabel}</p>
                  {selectedTenant?.tenant_id ? (
                    <p className="text-muted-foreground mt-2 font-mono text-xs break-all">
                      {selectedTenant.tenant_id}
                    </p>
                  ) : null}
                </div>
                <div>
                  <label
                    htmlFor="deletion-reason"
                    className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-widest uppercase"
                  >
                    Reason
                  </label>
                  <select
                    id="deletion-reason"
                    value={reason}
                    onChange={(event) => setReason(event.target.value as typeof reason)}
                    className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 text-sm outline-none focus:border-red-500/50"
                  >
                    <option value="workspace_offboarding">Workspace offboarding</option>
                    <option value="security_incident">Security incident</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="target-confirmation"
                    className="text-muted-foreground mb-2 block text-[10px] font-bold tracking-widest uppercase"
                  >
                    Type DELETE {selectedTenantId ?? user?.tenant_id ?? "workspace ID"}
                  </label>
                  <input
                    id="target-confirmation"
                    value={targetConfirmation}
                    onChange={(event) => setTargetConfirmation(event.target.value)}
                    placeholder={`DELETE ${selectedTenantId ?? user?.tenant_id ?? "workspace ID"}`}
                    autoComplete="off"
                    className="bg-muted border-glass-border text-foreground w-full rounded-xl border px-4 py-3 font-mono text-sm outline-none focus:border-red-500/50"
                  />
                </div>
              </div>

              <div className="flex gap-4">
                <button
                  onClick={closeConfirmation}
                  className="bg-muted text-muted-foreground hover:bg-muted/80 border-glass-border flex-1 rounded-xl border px-6 py-3 text-sm font-bold tracking-widest uppercase transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={handleWipe}
                  disabled={
                    submitting ||
                    (!selectedTenantId && !user?.tenant_id) ||
                    targetConfirmation.trim() !==
                      `DELETE ${selectedTenantId ?? user?.tenant_id ?? ""}`
                  }
                  className="disabled:bg-muted disabled:text-muted-foreground flex flex-1 items-center justify-center gap-2 rounded-xl bg-red-600 px-6 py-3 text-sm font-bold tracking-widest text-white uppercase shadow-lg shadow-red-500/25 transition-all hover:bg-red-500"
                >
                  {submitting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                  Wipe Data
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
