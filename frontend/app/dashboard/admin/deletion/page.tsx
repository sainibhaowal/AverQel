"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Search, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import toast from "react-hot-toast";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import AverQelLoading from "@/app/components/ui/AverQelLoading";
import RoundedSelect from "@/app/components/ui/RoundedSelect";
import { useAuth } from "@/app/context/AuthContext";
import { fetchWithAuth } from "@/lib/api";
import { hasAdminRole } from "@/lib/roles";

interface UserSummary {
  user_id: string;
  tenant_id: string;
  tenant_name: string | null;
  email: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface UserListResponse {
  items: UserSummary[];
}

interface DeleteResponse {
  pending_storage_cleanup_count?: number;
}

interface StorageCleanupJob {
  id: string;
  tenant_id: string;
  status: "pending" | "failed";
  attempts: number;
  next_attempt_at: string;
  created_at: string;
}

interface StorageCleanupResponse {
  items: StorageCleanupJob[];
}

interface TenantPurgeRequest {
  deletion_id: string;
  tenant_id: string;
  status: string;
  scope: string;
  reason: string | null;
  can_approve: boolean;
  can_self_approve: boolean;
  can_cancel: boolean;
  self_approval_not_before: string | null;
  requested_at: string;
}

interface PlatformAdminAccessResponse {
  allowed: boolean;
  reason?:
    | "ADMIN_ROLE_REQUIRED"
    | "PLATFORM_ADMIN_ALLOWLIST_REQUIRED"
    | "ADMIN_MFA_SETUP_REQUIRED"
    | "ADMIN_MFA_REQUIRED"
    | null;
}

type PlatformAdminAccessState = "checking" | "allowed" | "denied" | "unavailable";

export default function DeletionPage() {
  const { user } = useAuth();
  const isAdmin = hasAdminRole(user?.roles);
  const [adminAccessState, setAdminAccessState] = useState<PlatformAdminAccessState>("checking");
  const [adminAccessReason, setAdminAccessReason] = useState<string | null>(null);
  const [adminAccessError, setAdminAccessError] = useState<string | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [loading, setLoading] = useState(true);
  const [cleanupJobs, setCleanupJobs] = useState<StorageCleanupJob[]>([]);
  const [loadingCleanup, setLoadingCleanup] = useState(true);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [purgeRequests, setPurgeRequests] = useState<TenantPurgeRequest[]>([]);
  const [loadingPurgeRequests, setLoadingPurgeRequests] = useState(false);
  const [purgeConfirmation, setPurgeConfirmation] = useState("");
  const [purgeReason, setPurgeReason] = useState<"workspace_offboarding" | "security_incident">(
    "security_incident",
  );
  const [purgeActionId, setPurgeActionId] = useState<string | null>(null);

  const selectedUser = useMemo(
    () => users.find((item) => item.user_id === selectedUserId) ?? null,
    [selectedUserId, users],
  );
  const visibleUsers = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return users;
    return users.filter(
      (item) =>
        item.email.toLowerCase().includes(term) ||
        (item.tenant_name ?? "").toLowerCase().includes(term) ||
        item.tenant_id.toLowerCase().includes(term),
    );
  }, [search, users]);
  const expectedConfirmation = selectedUser ? `DELETE ${selectedUser.email}` : "";
  const expectedPurgeConfirmation = selectedUser ? `DELETE ${selectedUser.tenant_id}` : "";
  const selectedTenantAccountCount = selectedUser
    ? users.filter((item) => item.tenant_id === selectedUser.tenant_id).length
    : 0;

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const response = (await fetchWithAuth("/admin/users")) as Response;
      if (!response.ok) throw new Error(`Could not load accounts (${response.status}).`);
      const payload = (await response.json()) as Partial<UserListResponse>;
      const items = Array.isArray(payload.items) ? payload.items : [];
      setUsers(items);
      setSelectedUserId((current) =>
        current && items.some((item) => item.user_id === current)
          ? current
          : (items[0]?.user_id ?? null),
      );
    } catch (error) {
      console.error("Failed to load accounts for deletion", error);
      toast.error(error instanceof Error ? error.message : "Could not load accounts.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCleanupJobs = useCallback(async () => {
    setLoadingCleanup(true);
    try {
      const response = (await fetchWithAuth("/admin/storage-cleanup?limit=200")) as Response;
      if (!response.ok) throw new Error(`Could not load file cleanup queue (${response.status}).`);
      const payload = (await response.json()) as Partial<StorageCleanupResponse>;
      setCleanupJobs(Array.isArray(payload.items) ? payload.items : []);
    } catch (error) {
      console.error("Failed to load storage cleanup queue", error);
      toast.error(error instanceof Error ? error.message : "Could not load file cleanup queue.");
    } finally {
      setLoadingCleanup(false);
    }
  }, []);

  const loadPurgeRequests = useCallback(async () => {
    if (!selectedUser) {
      setPurgeRequests([]);
      return;
    }
    setLoadingPurgeRequests(true);
    try {
      const params = new URLSearchParams({
        limit: "50",
        target_tenant_id: selectedUser.tenant_id,
      });
      const response = (await fetchWithAuth(
        `/admin/data-deletions?${params.toString()}`,
      )) as Response;
      if (!response.ok) throw new Error(`Could not load purge requests (${response.status}).`);
      const payload = (await response.json()) as { items?: TenantPurgeRequest[] };
      setPurgeRequests(Array.isArray(payload.items) ? payload.items : []);
    } catch (error) {
      console.error("Failed to load tenant purge requests", error);
      toast.error(error instanceof Error ? error.message : "Could not load purge requests.");
    } finally {
      setLoadingPurgeRequests(false);
    }
  }, [selectedUser]);

  const checkPlatformAdminAccess = useCallback(async () => {
    setAdminAccessState("checking");
    setAdminAccessReason(null);
    setAdminAccessError(null);
    try {
      const response = (await fetchWithAuth("/admin/access")) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          payload?.error?.message || `Could not verify platform admin access (${response.status}).`,
        );
      }
      const payload = (await response.json()) as PlatformAdminAccessResponse;
      if (payload.allowed) {
        setAdminAccessState("allowed");
        return true;
      }
      setAdminAccessReason(payload.reason ?? "FORBIDDEN");
      setAdminAccessState("denied");
      return false;
    } catch (error) {
      setAdminAccessError(
        error instanceof Error ? error.message : "Could not verify platform admin access.",
      );
      setAdminAccessState("unavailable");
      return false;
    }
  }, []);

  const loadAuthorizedPageData = useCallback(async () => {
    setLoading(true);
    setLoadingCleanup(true);
    const allowed = await checkPlatformAdminAccess();
    if (!allowed) {
      setLoading(false);
      setLoadingCleanup(false);
      return;
    }
    await Promise.all([loadUsers(), loadCleanupJobs()]);
  }, [checkPlatformAdminAccess, loadCleanupJobs, loadUsers]);

  useEffect(() => {
    if (isAdmin) {
      queueMicrotask(() => void loadAuthorizedPageData());
    } else {
      queueMicrotask(() => {
        setAdminAccessState("denied");
        setAdminAccessReason("ADMIN_ROLE_REQUIRED");
        setLoading(false);
        setLoadingCleanup(false);
      });
    }
  }, [isAdmin, loadAuthorizedPageData]);

  useEffect(() => {
    if (adminAccessState === "allowed" && selectedUser) {
      queueMicrotask(() => void loadPurgeRequests());
    }
  }, [adminAccessState, loadPurgeRequests, selectedUser]);

  const eraseAccount = async () => {
    if (!selectedUser || confirmation.trim() !== expectedConfirmation) return;
    setDeleting(true);
    try {
      const response = (await fetchWithAuth(`/admin/users/${selectedUser.user_id}`, {
        method: "DELETE",
        body: JSON.stringify({ confirmation: expectedConfirmation }),
      })) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          payload?.error?.message ||
            payload?.message ||
            `Account deletion failed (${response.status}).`,
        );
      }
      const result = (await response.json().catch(() => ({}))) as DeleteResponse;
      const pending = Number(result.pending_storage_cleanup_count ?? 0);
      setUsers((current) => current.filter((item) => item.user_id !== selectedUser.user_id));
      setSelectedUserId(null);
      setPurgeRequests([]);
      setConfirmation("");
      toast.success(
        pending > 0
          ? `Account erased. ${pending} stored file${pending === 1 ? " is" : "s are"} queued for background cleanup.`
          : "Account and account-owned data erased.",
      );
      await loadCleanupJobs();
    } catch (error) {
      console.error("Account erasure failed", error);
      toast.error(error instanceof Error ? error.message : "Account deletion failed.");
    } finally {
      setDeleting(false);
    }
  };

  const retryCleanup = async (job: StorageCleanupJob) => {
    setRetryingJobId(job.id);
    try {
      const response = (await fetchWithAuth(`/admin/storage-cleanup/${job.id}/retry`, {
        method: "POST",
      })) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.error?.message || `Could not retry cleanup (${response.status}).`);
      }
      toast.success("File cleanup has been queued for retry.");
      await loadCleanupJobs();
    } catch (error) {
      console.error("Could not retry storage cleanup", error);
      toast.error(error instanceof Error ? error.message : "Could not retry file cleanup.");
    } finally {
      setRetryingJobId(null);
    }
  };

  const requestTenantPurge = async () => {
    if (
      !selectedUser ||
      selectedTenantAccountCount !== 1 ||
      purgeConfirmation.trim() !== expectedPurgeConfirmation
    ) {
      return;
    }
    setPurgeActionId("request");
    try {
      const response = (await fetchWithAuth("/admin/data-deletions", {
        method: "POST",
        body: JSON.stringify({
          reason: purgeReason,
          target_tenant_id: selectedUser.tenant_id,
          target_confirmation: expectedPurgeConfirmation,
        }),
      })) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.error?.message || `Could not request purge (${response.status}).`);
      }
      setPurgeConfirmation("");
      toast.success("Purge request created with a delayed single-admin approval window.");
      await loadPurgeRequests();
    } catch (error) {
      console.error("Could not request tenant purge", error);
      toast.error(error instanceof Error ? error.message : "Could not request purge.");
    } finally {
      setPurgeActionId(null);
    }
  };

  const updatePurgeRequest = async (
    request: TenantPurgeRequest,
    action: "approve" | "self-approve" | "cancel",
  ) => {
    setPurgeActionId(request.deletion_id);
    try {
      const params = new URLSearchParams({ target_tenant_id: request.tenant_id });
      const response = (await fetchWithAuth(
        `/admin/data-deletions/${request.deletion_id}/${action}?${params.toString()}`,
        { method: "POST" },
      )) as Response;
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          payload?.error?.message || `Could not ${action} purge (${response.status}).`,
        );
      }
      toast.success(
        action === "cancel"
          ? "Purge request cancelled."
          : "Purge approved and queued for processing.",
      );
      await loadPurgeRequests();
    } catch (error) {
      console.error(`Could not ${action} tenant purge`, error);
      toast.error(error instanceof Error ? error.message : `Could not ${action} purge.`);
    } finally {
      setPurgeActionId(null);
    }
  };

  const formatTimestamp = (value: string | null) => {
    if (!value) return "Never recorded";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? "Not available"
      : `${new Intl.DateTimeFormat("en-GB", {
          timeZone: "UTC",
          dateStyle: "medium",
          timeStyle: "short",
        }).format(date)} UTC`;
  };

  return (
    <div className="dashboard-theme-scope deletion-theme-scope w-full space-y-8">
      <DashboardSectionHeader
        title="Data Deletion"
        subtitle="Erase One User Account and Its Owned Data"
        icon={Trash2}
        accentClassName="bg-red-500 text-red-400"
        accentGlowClassName="shadow-[0_0_18px_rgba(239,68,68,0.28)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
      />

      {!isAdmin ? (
        <section className="glass-card text-muted-foreground p-6 text-sm">
          This account-erasure workflow is available only to an authorized platform administrator.
        </section>
      ) : adminAccessState === "checking" ? (
        <section className="glass-card p-6">
          <AverQelLoading
            label="Checking platform administrator access…"
            size="compact"
            className="justify-center"
          />
        </section>
      ) : adminAccessState === "denied" ? (
        <section className="glass-card space-y-3 p-6" role="status">
          <h2 className="text-foreground text-sm font-semibold">
            Platform administrator access required
          </h2>
          {adminAccessReason === "PLATFORM_ADMIN_ALLOWLIST_REQUIRED" ? (
            <p className="text-muted-foreground text-sm leading-6">
              This account has the admin role, but its email is not configured in the deployment’s
              platform-admin allowlist. Ask the AverQel deployment operator to authorize this
              account.
            </p>
          ) : adminAccessReason === "ADMIN_MFA_SETUP_REQUIRED" ? (
            <div className="text-muted-foreground space-y-2 text-sm leading-6">
              <p>Set up authenticator MFA before using platform administration.</p>
              <Link
                href="/dashboard/settings/profile"
                className="text-primary inline-flex font-medium underline-offset-4 hover:underline"
              >
                Open account security settings
              </Link>
            </div>
          ) : adminAccessReason === "ADMIN_MFA_REQUIRED" ? (
            <p className="text-muted-foreground text-sm leading-6">
              Sign out and sign in again, then complete the authenticator challenge to establish an
              MFA-verified administrator session.
            </p>
          ) : (
            <p className="text-muted-foreground text-sm leading-6">
              This account is not authorized for platform-wide account deletion and cleanup.
            </p>
          )}
        </section>
      ) : adminAccessState === "unavailable" ? (
        <section className="glass-card space-y-3 p-6" role="alert">
          <h2 className="text-foreground text-sm font-semibold">
            Could not check platform administrator access
          </h2>
          <p className="text-muted-foreground text-sm">
            {adminAccessError ?? "The access check could not be completed."}
          </p>
          <button
            type="button"
            onClick={() => void loadAuthorizedPageData()}
            className="theme-panel-muted text-foreground border-glass-border inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
          >
            <RefreshCw size={14} /> Try again
          </button>
        </section>
      ) : (
        <>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.8fr)]">
            <section className="glass-card min-w-0 space-y-5 p-5">
              <div>
                <h2 className="text-foreground text-sm font-semibold">Select an account</h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  Search by email or tenant. This action targets one person’s account across
                  AverQel.
                </p>
              </div>
              <label className="theme-panel-muted focus-within:border-primary/55 focus-within:ring-primary/10 flex items-center gap-3 rounded-xl px-4 py-3 focus-within:ring-2">
                <Search size={16} className="text-muted-foreground" />
                <span className="sr-only">Search accounts</span>
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search email or tenant"
                  className="search-shell-input text-foreground placeholder:text-muted-foreground w-full text-sm"
                />
              </label>

              <div className="max-h-[34rem] space-y-2 overflow-y-auto">
                {loading ? (
                  <AverQelLoading
                    label="Loading accounts…"
                    size="compact"
                    className="justify-center py-12"
                  />
                ) : visibleUsers.length ? (
                  visibleUsers.map((item) => (
                    <button
                      key={item.user_id}
                      type="button"
                      onClick={() => {
                        setSelectedUserId(item.user_id);
                        setPurgeRequests([]);
                        setConfirmation("");
                      }}
                      className={`deletion-account-option theme-panel-muted flex w-full items-start gap-3 rounded-xl border p-4 text-left transition ${
                        item.user_id === selectedUserId
                          ? "deletion-account-option-selected border-primary/50 bg-primary/10"
                          : "hover:border-glass-border border-transparent"
                      }`}
                    >
                      <UserRound size={17} className="text-primary mt-0.5 shrink-0" />
                      <span className="min-w-0 flex-1">
                        <span className="text-foreground block truncate text-sm font-medium">
                          {item.email}
                        </span>
                        <span className="text-muted-foreground mt-1 block truncate text-xs">
                          {item.tenant_name || item.tenant_id}
                        </span>
                      </span>
                      <span
                        className={`deletion-account-status shrink-0 rounded-lg px-2 py-1 text-[10px] font-semibold uppercase ${
                          item.is_active
                            ? "deletion-account-status-active"
                            : "deletion-account-status-disabled"
                        }`}
                      >
                        {item.is_active ? "Active" : "Disabled"}
                      </span>
                    </button>
                  ))
                ) : (
                  <p className="text-muted-foreground py-10 text-center text-sm">
                    {users.length ? "No accounts match this search." : "No accounts found."}
                  </p>
                )}
              </div>
            </section>

            <section className="glass-card min-w-0 space-y-5 p-5">
              <div className="flex items-start gap-3">
                <AlertTriangle size={20} className="mt-0.5 shrink-0 text-red-400" />
                <div>
                  <h2 className="text-foreground text-sm font-semibold">
                    Permanent account erasure
                  </h2>
                  <p className="text-muted-foreground mt-1 text-sm leading-6">
                    Deletes the selected account and its account-owned records, including documents,
                    queries, conversations, provider settings, support tickets, feedback, and
                    personal connections. Other users’ records in a shared tenant remain.
                  </p>
                </div>
              </div>

              {selectedUser ? (
                <div className="deletion-selected-account theme-panel-muted space-y-3 rounded-xl p-4">
                  <div>
                    <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                      Selected account
                    </p>
                    <p className="text-foreground mt-1 text-sm font-medium break-all">
                      {selectedUser.email}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                      Account created
                    </p>
                    <p className="text-foreground mt-1 text-sm">
                      {formatTimestamp(selectedUser.created_at)}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-[10px] font-bold tracking-widest uppercase">
                      Last successful sign-in
                    </p>
                    <p className="text-foreground mt-1 text-sm">
                      {formatTimestamp(selectedUser.last_login_at)}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="theme-panel-muted text-muted-foreground rounded-xl p-5 text-sm">
                  Select an account to review its deletion details.
                </div>
              )}

              <div className="deletion-warning-note text-muted-foreground rounded-xl border border-amber-500/25 bg-amber-500/5 p-4 text-xs leading-5">
                Database records are removed in this operation. Stored files are queued for
                background deletion and may take time to finish. Security audit events are retained
                in a minimal, anonymized form; backups and copies held by external providers follow
                their own retention and deletion controls. This action also requires an
                administrator sign-in completed with MFA in the last 10 minutes.
              </div>

              <label className="deletion-form-label text-muted-foreground block text-xs font-semibold">
                Type{" "}
                <span className="text-foreground font-mono">
                  {expectedConfirmation || "DELETE email"}
                </span>{" "}
                to confirm
                <input
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  disabled={!selectedUser || deleting}
                  className="deletion-confirmation-input theme-panel-muted text-foreground border-glass-border focus:border-primary/50 mt-2 w-full rounded-xl border px-4 py-3 text-sm outline-none disabled:opacity-50"
                  autoComplete="off"
                />
              </label>

              <button
                type="button"
                onClick={() => void eraseAccount()}
                disabled={
                  !selectedUser ||
                  confirmation.trim() !== expectedConfirmation ||
                  deleting ||
                  loading
                }
                className="deletion-danger-action flex w-full items-center justify-center gap-2 rounded-xl bg-red-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-red-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                {deleting ? "Erasing account…" : "Erase account and owned data"}
              </button>
            </section>
          </div>
          <section className="glass-card space-y-5 p-5">
            <div>
              <h2 className="text-foreground text-sm font-semibold">Tenant-content purge</h2>
              <p className="text-muted-foreground mt-1 text-sm leading-6">
                This removes tenant content while retaining user accounts, provider settings,
                support and feedback records, and audit records. Use account erasure above to delete
                one person’s account and owned data. A second administrator can approve this tenant
                purge immediately; a sole administrator can approve after the displayed delay. A
                recent MFA sign-in is required to request, approve, or cancel.
              </p>
            </div>
            {selectedUser ? (
              <>
                <p className="deletion-tenant-target theme-panel-muted rounded-lg p-3 text-xs text-slate-300">
                  Target account: <span className="font-semibold">{selectedUser.email}</span>
                  <br />
                  Isolated tenant: <span className="font-mono">{selectedUser.tenant_id}</span>
                  {selectedTenantAccountCount > 1 ? (
                    <span className="mt-2 block text-amber-300">
                      This tenant has {selectedTenantAccountCount} accounts. Full purge is disabled
                      to protect the other accounts.
                    </span>
                  ) : null}
                </p>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="deletion-form-label min-w-48 text-xs font-semibold text-slate-400">
                    Reason
                    <RoundedSelect
                      label="Deletion reason"
                      value={purgeReason}
                      onChange={(reason) =>
                        setPurgeReason(reason as "workspace_offboarding" | "security_incident")
                      }
                      options={[
                        { value: "security_incident", label: "Security incident" },
                        { value: "workspace_offboarding", label: "Tenant-content offboarding" },
                      ]}
                      className="mt-1 w-full"
                      triggerClassName="w-full px-3 py-2"
                    />
                  </label>
                  <label className="deletion-form-label min-w-64 flex-1 text-xs font-semibold text-slate-400">
                    Type {expectedPurgeConfirmation || "DELETE tenant ID"}
                    <input
                      value={purgeConfirmation}
                      onChange={(event) => setPurgeConfirmation(event.target.value)}
                      disabled={selectedTenantAccountCount !== 1 || purgeActionId === "request"}
                      className="deletion-confirmation-input theme-panel-muted text-foreground border-glass-border mt-1 w-full rounded-lg border px-3 py-2 font-mono text-xs"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => void requestTenantPurge()}
                    disabled={
                      selectedTenantAccountCount !== 1 ||
                      purgeConfirmation.trim() !== expectedPurgeConfirmation ||
                      purgeActionId !== null
                    }
                    className="deletion-danger-action rounded-lg bg-red-500 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    {purgeActionId === "request" ? "Requesting…" : "Request tenant-content purge"}
                  </button>
                </div>
              </>
            ) : (
              <p className="text-muted-foreground text-sm">Select an account above.</p>
            )}
            <div className="space-y-2">
              <h3 className="text-foreground text-xs font-semibold">Purge requests</h3>
              {loadingPurgeRequests ? (
                <AverQelLoading
                  label="Loading requests…"
                  size="compact"
                  className="justify-start"
                />
              ) : purgeRequests.length ? (
                purgeRequests.map((request) => (
                  <div
                    key={request.deletion_id}
                    className="theme-panel-muted flex flex-wrap items-center justify-between gap-3 rounded-lg p-3"
                  >
                    <div className="text-xs">
                      <p className="text-foreground font-medium">
                        {request.scope.replaceAll("_", " ")} · {request.status.replaceAll("_", " ")}
                      </p>
                      <p className="text-muted-foreground mt-1">
                        Requested {formatTimestamp(request.requested_at)}
                        {request.self_approval_not_before
                          ? ` · Solo approval after ${formatTimestamp(request.self_approval_not_before)}`
                          : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {request.can_approve ? (
                        <button
                          type="button"
                          onClick={() => void updatePurgeRequest(request, "approve")}
                          disabled={purgeActionId === request.deletion_id}
                          className="deletion-approve-action rounded-lg border border-amber-400/30 px-3 py-2 text-xs text-amber-200 disabled:opacity-50"
                        >
                          Approve
                        </button>
                      ) : null}
                      {request.can_self_approve ? (
                        <button
                          type="button"
                          onClick={() => void updatePurgeRequest(request, "self-approve")}
                          disabled={purgeActionId === request.deletion_id}
                          className="deletion-secondary-danger-action rounded-lg border border-red-400/30 px-3 py-2 text-xs text-red-200 disabled:opacity-50"
                        >
                          Approve after delay
                        </button>
                      ) : null}
                      {request.can_cancel ? (
                        <button
                          type="button"
                          onClick={() => void updatePurgeRequest(request, "cancel")}
                          disabled={purgeActionId === request.deletion_id}
                          className="deletion-neutral-action rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 disabled:opacity-50"
                        >
                          Cancel request
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground text-xs">No purge requests for this account.</p>
              )}
            </div>
          </section>
          <section className="glass-card space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-foreground text-sm font-semibold">Stored-file cleanup</h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  Pending and failed background file removals across accounts. Object paths and
                  provider errors are hidden.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void loadCleanupJobs()}
                disabled={loadingCleanup}
                className="deletion-refresh-action theme-chip flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold disabled:opacity-50"
              >
                <RefreshCw size={14} className={loadingCleanup ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
            {loadingCleanup ? (
              <AverQelLoading
                label="Loading cleanup queue…"
                size="compact"
                className="justify-start py-4"
              />
            ) : cleanupJobs.length ? (
              <div className="space-y-2">
                {cleanupJobs.map((job) => (
                  <div
                    key={job.id}
                    className="theme-panel-muted flex flex-wrap items-center justify-between gap-3 rounded-xl p-4"
                  >
                    <div className="min-w-0">
                      <p className="text-foreground text-sm font-medium">
                        {job.status === "failed" ? "Needs retry" : "Waiting for cleanup worker"}
                      </p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        Tenant {job.tenant_id.slice(0, 8)}… · {job.attempts} attempt
                        {job.attempts === 1 ? "" : "s"} · next try{" "}
                        {formatTimestamp(job.next_attempt_at)}
                      </p>
                    </div>
                    {job.status === "failed" ? (
                      <button
                        type="button"
                        onClick={() => void retryCleanup(job)}
                        disabled={retryingJobId === job.id}
                        className="deletion-retry-action rounded-lg border border-amber-400/30 px-3 py-2 text-xs font-semibold text-amber-300 transition hover:bg-amber-400/10 disabled:opacity-50"
                      >
                        {retryingJobId === job.id ? "Queueing…" : "Retry cleanup"}
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-muted-foreground py-4 text-sm">
                No pending or failed file cleanup jobs.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
