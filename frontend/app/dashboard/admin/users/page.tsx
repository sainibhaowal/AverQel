"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import toast from "react-hot-toast";

import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  MessageSquare,
  Shield,
  ShieldCheck,
  UserRound,
  UserRoundCheck,
  UserRoundX,
  Users,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import { fetchWithAuth } from "@/lib/api";
import { getRoleLabel } from "@/lib/roles";
import ConfirmationModal from "@/app/components/ui/ConfirmationModal";

interface UserStats {
  documents_count: number;
  queries_count: number;
  conversations_count: number;
  comments_count: number;
  pinned_findings_count: number;
  providers_count: number;
  storage_bytes: number;
}

interface UserSummary {
  user_id: string;
  tenant_id: string;
  tenant_name?: string | null;
  email: string;
  is_active: boolean;
  totp_enabled: boolean;
  roles: string[];
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  stats: UserStats;
}

interface UserDetailResponse {
  user: UserSummary;
  recent_activity: Array<{
    id: string;
    action: string;
    resource_type: string;
    status: string;
    created_at: string;
    details: Record<string, string>;
  }>;
}

interface UserListResponse {
  items: UserSummary[];
}

const formatDate = (value: string | null) => {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
};

const statItems = (stats: UserStats) => [
  { label: "Documents", value: stats.documents_count },
  { label: "Queries", value: stats.queries_count },
  { label: "Chats", value: stats.conversations_count },
  { label: "Comments", value: stats.comments_count },
  { label: "Pins", value: stats.pinned_findings_count },
  { label: "Providers", value: stats.providers_count ?? 0 },
  { label: "Storage MB", value: Math.round((stats.storage_bytes ?? 0) / 1024 / 1024) },
];

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [detail, setDetail] = useState<UserDetailResponse | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  // Modal State
  const [confirmConfig, setConfirmConfig] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    variant: "danger" | "warning" | "info" | "success";
    onConfirm: () => Promise<void>;
  }>({
    isOpen: false,
    title: "",
    message: "",
    confirmLabel: "",
    variant: "danger",
    onConfirm: async () => {},
  });

  const selectedUser = useMemo(
    () => users.find((user) => user.user_id === selectedUserId) ?? detail?.user ?? null,
    [detail?.user, selectedUserId, users],
  );

  const loadUsers = useCallback(async (): Promise<string | null> => {
    setLoadingUsers(true);
    try {
      const res = (await fetchWithAuth("/admin/users")) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load users (${res.status})`);
      }
      const data = (await res.json()) as Partial<UserListResponse>;
      const items = Array.isArray(data.items) ? data.items : [];
      setUsers(items);
      let nextSelectedUserId: string | null = null;
      setSelectedUserId((current) => {
        if (current && items.some((item) => item.user_id === current)) {
          nextSelectedUserId = current;
          return current;
        }
        nextSelectedUserId = items[0]?.user_id ?? null;
        return nextSelectedUserId;
      });
      return nextSelectedUserId;
    } catch (error) {
      console.error(error);
      toast.error("Failed to load users.");
      return null;
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const loadDetail = useCallback(async (userId: string) => {
    setLoadingDetail(true);
    try {
      const res = (await fetchWithAuth(`/admin/users/${userId}`)) as Response;
      if (!res.ok) {
        throw new Error(`Failed to load user details (${res.status})`);
      }
      setDetail((await res.json()) as UserDetailResponse);
    } catch (error) {
      console.error(error);
      toast.error("Failed to load user details.");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    if (!selectedUserId) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedUserId);
  }, [loadDetail, selectedUserId]);

  const refreshAll = async (userId?: string) => {
    const refreshedSelectedUserId = await loadUsers();
    const targetUserId = userId ?? refreshedSelectedUserId;
    if (targetUserId) {
      await loadDetail(targetUserId);
    } else {
      setDetail(null);
    }
  };

  const runAction = async (
    actionKey: string,
    request: () => Promise<Response>,
    successMessage: string,
  ) => {
    setBusyAction(actionKey);
    try {
      const res = await request();
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error?.message || `Request failed (${res.status})`);
      }
      const body = (await res.json().catch(() => null)) as {
        deleted_counts?: { storage_cleanup_pending?: number };
      } | null;
      toast.success(successMessage);
      const pending = body?.deleted_counts?.storage_cleanup_pending ?? 0;
      if (actionKey.startsWith("delete:") && pending > 0) {
        toast(`Storage cleanup queued for ${pending} object${pending === 1 ? "" : "s"}.`, {
          icon: "🧹",
        });
      }
      await refreshAll();
    } catch (error) {
      console.error(error);
      toast.error(error instanceof Error ? error.message : "Action failed.");
    } finally {
      setBusyAction(null);
      setConfirmConfig((prev) => ({ ...prev, isOpen: false }));
    }
  };

  const triggerAction = (
    user: UserSummary,
    action: "disable" | "reactivate" | "logout" | "delete",
  ) => {
    const configs = {
      disable: {
        title: "Disable Account",
        message: `Are you sure you want to disable ${user.email}? The user will be immediately logged out and blocked from all services.`,
        confirmLabel: "Disable User",
        variant: "warning" as const,
        onConfirm: async () =>
          runAction(
            `disable:${user.user_id}`,
            async () =>
              (await fetchWithAuth(`/admin/users/${user.user_id}/disable`, {
                method: "POST",
              })) as Response,
            `${user.email} was disabled.`,
          ),
      },
      reactivate: {
        title: "Reactivate Account",
        message: `Reactivate ${user.email}? The user will be able to log in again immediately.`,
        confirmLabel: "Reactivate",
        variant: "success" as const,
        onConfirm: async () =>
          runAction(
            `reactivate:${user.user_id}`,
            async () =>
              (await fetchWithAuth(`/admin/users/${user.user_id}/reactivate`, {
                method: "POST",
              })) as Response,
            `${user.email} was reactivated.`,
          ),
      },
      logout: {
        title: "Force Logout",
        message: `Force ${user.email} to logout from all devices? Their current sessions will be invalidated.`,
        confirmLabel: "Force Logout",
        variant: "info" as const,
        onConfirm: async () =>
          runAction(
            `logout:${user.user_id}`,
            async () =>
              (await fetchWithAuth(`/admin/users/${user.user_id}/force-logout`, {
                method: "POST",
              })) as Response,
            `${user.email} was logged out.`,
          ),
      },
      delete: {
        title: "Permanently Delete User",
        message: `EXTREME CAUTION: This will permanently delete ${user.email} and all associated documents, queries, chats, and findings. This action cannot be undone.`,
        confirmLabel: "Delete Everything",
        variant: "danger" as const,
        onConfirm: async () =>
          runAction(
            `delete:${user.user_id}`,
            async () =>
              (await fetchWithAuth(`/admin/users/${user.user_id}`, {
                method: "DELETE",
              })) as Response,
            `${user.email} was permanently deleted.`,
          ),
      },
    };

    setConfirmConfig({
      isOpen: true,
      ...configs[action],
    });
  };

  return (
    <div className="space-y-6 pb-4">
      <DashboardSectionHeader
        title="User Control"
        subtitle="Platform Lifecycle Oversight"
        icon={Users}
        accentClassName="bg-indigo-500 text-indigo-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(99,102,241,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
        actions={
          <div className="theme-chip rounded-full px-4 py-2 text-xs font-semibold tracking-[0.18em] uppercase">
            Admin Console
          </div>
        }
      />

      <div className="pr-1">
        <div className="grid gap-6 lg:h-[calc(100dvh-15rem)] lg:min-h-0 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <section className="theme-panel flex flex-col rounded-[1.5rem] p-4 lg:h-[calc(100dvh-15rem)] lg:min-h-0">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-foreground text-sm font-bold tracking-[0.18em] uppercase">
                Users
              </h2>
              <button
                type="button"
                onClick={() => void loadUsers()}
                className="theme-chip rounded-full px-3 py-1.5 text-[10px] font-bold tracking-[0.18em] uppercase"
              >
                Refresh
              </button>
            </div>

            {loadingUsers ? (
              <div className="text-muted-foreground flex items-center gap-3 rounded-2xl px-4 py-8 text-sm">
                <Loader2 size={16} className="animate-spin" />
                Loading users...
              </div>
            ) : users.length === 0 ? (
              <div className="theme-panel-muted text-muted-foreground rounded-2xl px-4 py-8 text-center text-sm">
                No users found.
              </div>
            ) : (
              <div className="space-y-3 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
                {users.map((user) => {
                  const selected = user.user_id === selectedUserId;
                  return (
                    <button
                      key={user.user_id}
                      type="button"
                      onClick={() => setSelectedUserId(user.user_id)}
                      className={`w-full rounded-[1.2rem] border p-4 text-left transition ${
                        selected
                          ? "border-primary/35 bg-primary/10"
                          : "border-white/8 bg-white/[0.02] hover:border-white/16 hover:bg-white/[0.04]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-foreground truncate text-sm font-semibold">
                            {user.email}
                          </p>
                          <p className="text-muted-foreground mt-1 text-xs tracking-[0.16em] uppercase">
                            {user.roles.map((role) => getRoleLabel(role)).join(" · ")}
                          </p>
                          <p className="text-muted-foreground mt-2 text-[11px]">
                            {user.tenant_name || user.tenant_id}
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-[0.16em] uppercase ${
                            user.is_active
                              ? "bg-success/10 text-success"
                              : "bg-danger/10 text-danger"
                          }`}
                        >
                          {user.is_active ? "active" : "disabled"}
                        </span>
                      </div>
                      <div className="text-muted-foreground mt-3 flex items-center gap-3 text-[11px]">
                        <span>{user.stats.documents_count} docs</span>
                        <span>{user.stats.queries_count} queries</span>
                        <span>{user.totp_enabled ? "2FA on" : "2FA off"}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <section className="theme-panel min-w-0 rounded-[1.5rem] p-5 lg:h-[calc(100dvh-15rem)] lg:min-h-0 lg:overflow-hidden">
            {!selectedUser ? (
              <div className="theme-panel-muted text-muted-foreground flex min-h-[28rem] items-center justify-center rounded-[1.3rem] text-sm">
                Select a user to inspect and control the account.
              </div>
            ) : loadingDetail && !detail ? (
              <div className="text-muted-foreground flex min-h-[28rem] items-center justify-center gap-3 text-sm">
                <Loader2 size={16} className="animate-spin" />
                Loading user detail...
              </div>
            ) : (
              <div className="space-y-6 lg:flex lg:h-full lg:min-h-0 lg:flex-col">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <div className="theme-accent-pill flex h-12 w-12 shrink-0 items-center justify-center rounded-[1rem]">
                        <UserRound size={20} />
                      </div>
                      <div className="min-w-0">
                        <h2 className="text-foreground truncate text-xl font-semibold">
                          {selectedUser.email}
                        </h2>
                        <p className="text-muted-foreground text-sm">
                          Last login: {formatDate(selectedUser.last_login_at)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      <Link
                        href={`/dashboard/admin/support?user=${selectedUser.user_id}`}
                        className="theme-chip hover:bg-primary/20 flex items-center gap-2 rounded-full px-4 py-1 text-[10px] font-bold tracking-[0.18em] uppercase transition"
                      >
                        <MessageSquare size={12} className="text-primary" />
                        Support History
                      </Link>
                      {selectedUser.roles.map((role) => (
                        <span
                          key={role}
                          className="theme-chip rounded-full px-3 py-1 text-[10px] font-bold tracking-[0.18em] uppercase"
                        >
                          {getRoleLabel(role)}
                        </span>
                      ))}
                      <span className="theme-chip rounded-full px-3 py-1 text-[10px] font-bold tracking-[0.18em] uppercase">
                        {selectedUser.totp_enabled ? "2FA enabled" : "2FA disabled"}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {selectedUser.is_active ? (
                      <button
                        type="button"
                        disabled={busyAction?.startsWith("disable:")}
                        onClick={() => triggerAction(selectedUser, "disable")}
                        className="border-warning/25 text-warning hover:bg-warning/10 rounded-xl border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60"
                      >
                        {busyAction === `disable:${selectedUser.user_id}`
                          ? "Disabling..."
                          : "Disable"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={busyAction?.startsWith("reactivate:")}
                        onClick={() => triggerAction(selectedUser, "reactivate")}
                        className="border-success/25 text-success hover:bg-success/10 rounded-xl border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60"
                      >
                        {busyAction === `reactivate:${selectedUser.user_id}`
                          ? "Reactivating..."
                          : "Reactivate"}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busyAction?.startsWith("logout:")}
                      onClick={() => triggerAction(selectedUser, "logout")}
                      className="border-info/25 text-info hover:bg-info/10 rounded-xl border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60"
                    >
                      {busyAction === `logout:${selectedUser.user_id}`
                        ? "Forcing logout..."
                        : "Force Logout"}
                    </button>
                    <button
                      type="button"
                      disabled={busyAction?.startsWith("delete:")}
                      onClick={() => triggerAction(selectedUser, "delete")}
                      className="border-danger/25 text-danger hover:bg-danger/10 rounded-xl border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-60"
                    >
                      {busyAction === `delete:${selectedUser.user_id}`
                        ? "Deleting..."
                        : "Delete User"}
                    </button>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                  {statItems(selectedUser.stats).map((item) => (
                    <div
                      key={item.label}
                      className="theme-panel-muted min-w-0 rounded-[1.15rem] p-4"
                    >
                      <p className="text-muted-foreground text-[10px] font-bold tracking-[0.18em] uppercase">
                        {item.label}
                      </p>
                      <p className="text-foreground mt-2 text-2xl font-semibold">{item.value}</p>
                    </div>
                  ))}
                </div>

                <div className="grid gap-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[minmax(0,1fr)_18rem]">
                  <div className="theme-panel-muted min-w-0 rounded-[1.2rem] p-4 xl:min-h-0 xl:overflow-hidden">
                    <h3 className="text-foreground text-sm font-bold tracking-[0.18em] uppercase">
                      Recent Activity
                    </h3>
                    <div className="mt-4 max-h-[30rem] space-y-3 overflow-y-auto pr-1 xl:h-[calc(100dvh-29rem)] xl:max-h-none">
                      {loadingDetail ? (
                        <div className="text-muted-foreground flex items-center gap-2 text-sm">
                          <Loader2 size={14} className="animate-spin" />
                          Refreshing activity...
                        </div>
                      ) : detail?.recent_activity.length ? (
                        detail.recent_activity.map((item) => (
                          <div
                            key={item.id}
                            className="min-w-0 rounded-[1rem] border border-white/8 bg-white/[0.03] p-4"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-foreground text-sm font-semibold break-words">
                                  {item.action}
                                </p>
                                <p className="text-muted-foreground mt-1 text-xs">
                                  {item.resource_type} • {formatDate(item.created_at)}
                                </p>
                              </div>
                              <span
                                className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-[0.16em] uppercase ${
                                  item.status.toLowerCase() === "success"
                                    ? "bg-success/10 text-success"
                                    : item.status.toLowerCase() === "failed"
                                      ? "bg-danger/10 text-danger"
                                      : "text-muted-foreground bg-surface-2"
                                }`}
                              >
                                {item.status}
                              </span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-muted-foreground text-sm">
                          No recent audit activity for this user.
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="space-y-3 xl:min-h-0 xl:overflow-y-auto xl:pr-1">
                    <div className="theme-panel-muted rounded-[1.2rem] p-4">
                      <div className="flex items-center gap-3">
                        {selectedUser.is_active ? (
                          <UserRoundCheck className="text-success" size={18} />
                        ) : (
                          <UserRoundX className="text-danger" size={18} />
                        )}
                        <div>
                          <p className="text-foreground text-sm font-semibold">Account State</p>
                          <p className="text-muted-foreground text-xs">
                            {selectedUser.is_active
                              ? "Enabled and can log in"
                              : "Disabled and blocked"}
                          </p>
                          <p className="text-muted-foreground mt-2 text-[11px]">
                            {selectedUser.tenant_name || selectedUser.tenant_id}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="theme-panel-muted rounded-[1.2rem] p-4">
                      <div className="flex items-center gap-3">
                        {selectedUser.totp_enabled ? (
                          <ShieldCheck className="text-info" size={18} />
                        ) : (
                          <Shield className="text-muted-foreground" size={18} />
                        )}
                        <div>
                          <p className="text-foreground text-sm font-semibold">Two-Factor Auth</p>
                          <p className="text-muted-foreground text-xs">
                            {selectedUser.totp_enabled ? "Authenticator enabled" : "No 2FA enabled"}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="border-danger/20 bg-danger/5 rounded-[1.2rem] border p-4">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="text-danger mt-0.5" size={16} />
                        <div>
                          <p className="text-danger text-sm font-semibold">Destructive controls</p>
                          <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                            Delete removes the user account and user-owned documents, queries,
                            chats, comments, and pins. Use disable first when you only need a
                            temporary stop.
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="border-info/20 bg-info/5 rounded-[1.2rem] border p-4">
                      <div className="flex items-start gap-3">
                        <CheckCircle2 className="text-info mt-0.5" size={16} />
                        <div>
                          <p className="text-info text-sm font-semibold">Operational note</p>
                          <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
                            Force Logout invalidates active sessions immediately without deleting
                            data.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
        <ConfirmationModal
          isOpen={confirmConfig.isOpen}
          onClose={() => setConfirmConfig((prev) => ({ ...prev, isOpen: false }))}
          onConfirm={confirmConfig.onConfirm}
          title={confirmConfig.title}
          message={confirmConfig.message}
          confirmLabel={confirmConfig.confirmLabel}
          variant={confirmConfig.variant}
          loading={!!busyAction}
        />
      </div>
    </div>
  );
}
