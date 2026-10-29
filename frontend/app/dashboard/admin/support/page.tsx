"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import {
  MessageSquare,
  Search,
  Loader2,
  CheckCircle2,
  Clock,
  ChevronRight,
  LifeBuoy,
  AlertTriangle,
  Paperclip,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import ProfileAvatar from "@/app/components/profile/ProfileAvatar";
import RoundedSelect from "@/app/components/ui/RoundedSelect";
import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";
import { useSupportEncryption } from "@/app/dashboard/support/SupportEncryptionGate";
import SupportEncryptionMigration from "@/app/dashboard/admin/SupportEncryptionMigration";
import {
  decryptSupportAttachment,
  decryptSupportPayload,
  encryptSupportPayload,
} from "@/lib/supportEncryption";

interface Ticket {
  id: string;
  user_id?: string;
  user_email?: string | null;
  user_display_name?: string | null;
  user_avatar?: string | null;
  subject: string;
  description: string;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
  priority?: string;
  assigned_admin_id?: string | null;
  first_response_due_at?: string | null;
  resolution_due_at?: string | null;
  encrypted_payload?: string | null;
}

interface TicketDetail extends Ticket {
  user_email?: string | null;
  participants?: ConversationParticipant[];
  attachments?: Array<{
    id: string;
    filename: string;
    size_bytes: number;
    download_url: string;
    is_encrypted?: boolean;
    encrypted_metadata?: string | null;
  }>;
  messages: Array<{
    id: string;
    author_ref?: string | null;
    author_role: string;
    kind: string;
    body: string;
    encrypted_payload?: string | null;
    is_internal: boolean;
    created_at: string;
  }>;
}

interface ConversationParticipant {
  ref: string;
  display_name?: string | null;
  avatar?: string | null;
}

interface QueueUserProfile {
  user_id: string;
  display_name?: string | null;
  avatar?: string | null;
}

interface UserSummary {
  user_id: string;
  email: string;
  display_name?: string | null;
  avatar?: string | null;
  ticket_count: number;
  last_ticket_at: string;
  latest_tickets: Ticket[];
}

function SupportContent() {
  const { user } = useAuth();
  const authenticatedUserId = user?.id;
  const encryption = useSupportEncryption("admin");
  const cryptoContext = encryption.context;
  const searchParams = useSearchParams();
  const queryUserId = searchParams.get("user");
  const queryTicketId = searchParams.get("ticket");

  const [users, setUsers] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(queryUserId);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(queryTicketId);
  const [ticketDetails, setTicketDetails] = useState<Record<string, TicketDetail>>({});
  const [replyDraft, setReplyDraft] = useState("");
  const [visibility, setVisibility] = useState<"public" | "internal">("public");
  const [saving, setSaving] = useState(false);
  const [queueCounts, setQueueCounts] = useState({ open: 0, overdue: 0, total: 0 });
  const [statusFilter, setStatusFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [assignmentFilter, setAssignmentFilter] = useState("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [pageOffset, setPageOffset] = useState(0);
  const [hasMoreTickets, setHasMoreTickets] = useState(false);
  const loadRequestId = useRef(0);

  const loadData = useCallback(async () => {
    const requestId = ++loadRequestId.current;
    if (pageOffset === 0) setLoading(true);
    try {
      const query = new URLSearchParams({ limit: "100", offset: String(pageOffset) });
      if (statusFilter !== "all") query.set("status", statusFilter);
      if (priorityFilter !== "all") query.set("priority", priorityFilter);
      if (assignmentFilter === "mine" && authenticatedUserId)
        query.set("assigned_to", authenticatedUserId);
      if (assignmentFilter === "unassigned") query.set("unassigned_only", "true");
      if (overdueOnly) query.set("overdue_only", "true");
      if (searchQuery.trim()) query.set("search", searchQuery.trim());
      const res = await fetchWithAuth(`/support/admin/queue?${query.toString()}`);
      if (requestId !== loadRequestId.current) return;
      if (!res.ok) {
        throw new Error(
          res.status === 403
            ? "Your account is not authorized to review support tickets. Use an allowlisted platform-administrator account."
            : `Support queue could not be loaded (${res.status}).`,
        );
      }
      setLoadError(null);
      if (res.ok) {
        const data = await res.json();
        setQueueCounts({ open: data.open_count, overdue: data.overdue_count, total: data.total });
        setHasMoreTickets(pageOffset + data.items.length < data.total);
        const userProfiles = new Map<string, QueueUserProfile>(
          ((data.users ?? []) as QueueUserProfile[]).map((profile) => [profile.user_id, profile]),
        );
        const byUser = new Map<string, UserSummary>();
        const decryptedTickets = await Promise.all(
          (data.items as Ticket[]).map(async (ticket) => {
            if (!cryptoContext || !ticket.encrypted_payload) return ticket;
            return {
              ...ticket,
              ...(await decryptSupportPayload<{ subject: string; description: string }>(
                ticket.encrypted_payload,
                cryptoContext.privateKey,
                cryptoContext.keyId,
              )),
            };
          }),
        );
        for (const ticket of decryptedTickets) {
          const userId = ticket.user_id ?? "unknown";
          const email = ticket.user_email ?? "Unknown user";
          const profile = userProfiles.get(userId);
          const summary = byUser.get(userId) ?? {
            user_id: userId,
            email,
            display_name: profile?.display_name,
            avatar: profile?.avatar,
            ticket_count: 0,
            last_ticket_at: ticket.updated_at,
            latest_tickets: [],
          };
          summary.ticket_count += 1;
          summary.latest_tickets.push(ticket);
          if (ticket.updated_at > summary.last_ticket_at)
            summary.last_ticket_at = ticket.updated_at;
          byUser.set(userId, summary);
        }
        const queueUsers = [...byUser.values()];
        setUsers((current) => {
          if (pageOffset === 0) return queueUsers;
          const merged = new Map(
            current.map((item) => [
              item.user_id,
              { ...item, latest_tickets: [...item.latest_tickets] },
            ]),
          );
          for (const item of queueUsers) {
            const existing = merged.get(item.user_id);
            if (!existing) merged.set(item.user_id, item);
            else {
              existing.display_name = existing.display_name ?? item.display_name;
              existing.avatar = existing.avatar ?? item.avatar;
              const ids = new Set(existing.latest_tickets.map((ticket) => ticket.id));
              existing.latest_tickets.push(
                ...item.latest_tickets.filter((ticket) => !ids.has(ticket.id)),
              );
              existing.ticket_count = existing.latest_tickets.length;
              if (item.last_ticket_at > existing.last_ticket_at)
                existing.last_ticket_at = item.last_ticket_at;
            }
          }
          return [...merged.values()];
        });
        const ticketOwner =
          queryTicketId &&
          queueUsers.find((u: UserSummary) =>
            u.latest_tickets.some((ticket) => ticket.id === queryTicketId),
          );
        if (ticketOwner) {
          setSelectedUserId(ticketOwner.user_id);
        } else if (queueUsers.length > 0 && !selectedUserId) {
          setSelectedUserId(queueUsers[0].user_id);
        } else if (queryUserId && queueUsers.some((u: UserSummary) => u.user_id === queryUserId)) {
          setSelectedUserId(queryUserId);
        }
      }
    } catch (err) {
      if (requestId !== loadRequestId.current) return;
      console.error(err);
      setUsers([]);
      setSelectedUserId(null);
      setQueueCounts({ open: 0, overdue: 0, total: 0 });
      setHasMoreTickets(false);
      setLoadError(err instanceof Error ? err.message : "Failed to load support data.");
    } finally {
      if (requestId === loadRequestId.current) setLoading(false);
    }
  }, [
    queryUserId,
    queryTicketId,
    selectedUserId,
    statusFilter,
    priorityFilter,
    assignmentFilter,
    overdueOnly,
    searchQuery,
    pageOffset,
    authenticatedUserId,
    cryptoContext,
  ]);

  useEffect(() => {
    if (!encryption.ready || !cryptoContext) return;
    queueMicrotask(() => void loadData());
  }, [loadData, encryption.ready, cryptoContext]);

  const loadTicketDetail = useCallback(async (ticketId: string) => {
    try {
      const res = await fetchWithAuth(`/support/admin/tickets/${ticketId}`);
      if (!res.ok) throw new Error(`Ticket could not be loaded (${res.status})`);
      const detail = (await res.json()) as TicketDetail;
      if (!cryptoContext) throw new Error("Support encryption is locked.");
      const ticketContent = detail.encrypted_payload
        ? await decryptSupportPayload<{ subject: string; description: string }>(
            detail.encrypted_payload,
            cryptoContext.privateKey,
            cryptoContext.keyId,
          )
        : null;
      const messages = await Promise.all(
        detail.messages.map(async (message) =>
          message.encrypted_payload
            ? {
                ...message,
                ...(await decryptSupportPayload<{ body: string }>(
                  message.encrypted_payload,
                  cryptoContext.privateKey,
                  cryptoContext.keyId,
                )),
              }
            : message,
        ),
      );
      setTicketDetails((current) => ({
        ...current,
        [ticketId]: { ...detail, ...(ticketContent ?? {}), messages },
      }));
    } catch (err) {
      console.error(err);
      toast.error("Could not load this support conversation.");
    }
  }, [cryptoContext]);

  useEffect(() => {
    if (!encryption.ready || !cryptoContext) return;
    const ticketId = new URLSearchParams(window.location.search).get("ticket");
    if (ticketId) {
      queueMicrotask(() => void loadTicketDetail(ticketId));
    }
  }, [encryption.ready, cryptoContext, loadTicketDetail]);

  async function downloadAttachment(
    url: string,
    filename: string,
    isEncrypted = false,
    encryptedMetadata?: string | null,
  ) {
    try {
      if (!cryptoContext) throw new Error("Support encryption is locked.");
      const response = await fetchWithAuth(url);
      if (!response.ok) throw new Error(`Attachment download failed (${response.status})`);
      const downloaded = await response.blob();
      const file =
        isEncrypted && encryptedMetadata
          ? await decryptSupportAttachment(
              await downloaded.arrayBuffer(),
              encryptedMetadata,
              cryptoContext.privateKey,
              cryptoContext.keyId,
            )
          : { blob: downloaded, filename, contentType: downloaded.type };
      const objectUrl = URL.createObjectURL(file.blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = file.filename;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      console.error(error);
      toast.error("Could not download the attachment.");
    }
  }

  async function sendReply(ticketId: string) {
    if (!replyDraft.trim()) return;
    if (!cryptoContext) return;
    setSaving(true);
    try {
      const ticket = ticketDetails[ticketId];
      if (!ticket?.user_id) throw new Error("The ticket owner key is unavailable.");
      const recipients =
        visibility === "internal"
          ? [cryptoContext.ownPublicKey]
          : [
              cryptoContext.ownPublicKey,
              await readUserPublicKey(ticket.user_id),
            ];
      const res = await fetchWithAuth(`/support/admin/tickets/${ticketId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          encrypted_payload: await encryptSupportPayload({ body: replyDraft.trim() }, recipients),
          visibility,
        }),
      });
      if (!res.ok) throw new Error(`Reply failed (${res.status})`);
      await res.json();
      await loadTicketDetail(ticketId);
      setReplyDraft("");
      toast.success(visibility === "public" ? "Reply sent to the user." : "Internal note saved.");
      void loadData();
    } catch (err) {
      console.error(err);
      toast.error("Could not send this message.");
    } finally {
      setSaving(false);
    }
  }

  async function readUserPublicKey(userId: string) {
    const response = await fetchWithAuth(`/support/encryption/users/${userId}/public-key`);
    if (!response.ok) throw new Error("The user has not initialized encrypted support yet.");
    return (await response.json()) as { key_id: string; public_key: string };
  }

  const handleUpdateStatus = async (ticketId: string, newStatus: string) => {
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/support/admin/tickets/${ticketId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(`Status update failed (${res.status})`);
      toast.success(`Status updated to ${newStatus.replace("_", " ")}`);
      void loadData();
      if (selectedTicketId === ticketId) void loadTicketDetail(ticketId);
    } catch (err) {
      console.error(err);
      toast.error("Failed to update status.");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdatePriority = async (ticketId: string, priority: string) => {
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/support/admin/tickets/${ticketId}`, {
        method: "PATCH",
        body: JSON.stringify({ priority }),
      });
      if (!res.ok) throw new Error(`Priority update failed (${res.status})`);
      toast.success("Priority updated.");
      void loadData();
    } catch (err) {
      console.error(err);
      toast.error("Could not update priority.");
    } finally {
      setSaving(false);
    }
  };

  const assignToMe = async (ticketId: string) => {
    if (!user?.id) return;
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/support/admin/tickets/${ticketId}`, {
        method: "PATCH",
        body: JSON.stringify({ assigned_admin_id: user?.id }),
      });
      if (!res.ok) throw new Error(`Assignment failed (${res.status})`);
      toast.success("Ticket assigned to you.");
      void loadData();
    } catch (err) {
      console.error(err);
      toast.error("Could not assign ticket.");
    } finally {
      setSaving(false);
    }
  };

  const selectedDetail = selectedTicketId ? ticketDetails[selectedTicketId] : undefined;
  const selectedUserBase = users.find(
    (u) => u.user_id === (selectedDetail?.user_id ?? selectedUserId),
  );
  const selectedUser = selectedUserBase
    ? selectedDetail?.user_id === selectedUserBase.user_id &&
      !selectedUserBase.latest_tickets.some((ticket) => ticket.id === selectedDetail.id)
      ? {
          ...selectedUserBase,
          latest_tickets: [selectedDetail, ...selectedUserBase.latest_tickets],
        }
      : selectedUserBase
    : selectedDetail?.user_email && selectedDetail.user_id
      ? {
          user_id: selectedDetail.user_id,
          email: selectedDetail.user_email,
          ticket_count: 1,
          last_ticket_at: selectedDetail.updated_at,
          latest_tickets: [selectedDetail],
        }
      : undefined;
  // Ticket text is encrypted, so the API can search only account metadata.
  const filteredUsers = users;

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case "open":
        return <Clock className="text-teal-700 dark:text-teal-300" size={14} />;
      case "in_progress":
        return <Loader2 className="animate-spin text-amber-700 dark:text-amber-300" size={14} />;
      case "resolved":
        return <CheckCircle2 className="text-emerald-700 dark:text-emerald-300" size={14} />;
      case "closed":
        return <CheckCircle2 className="text-muted-foreground" size={14} />;
      default:
        return <Clock size={14} />;
    }
  };

  if (!encryption.ready || !cryptoContext) return encryption.panel;

  return (
    <div className="dashboard-theme-scope flex min-h-[calc(100svh-14rem)] w-full flex-col lg:h-[calc(100svh-14rem)]">
      <DashboardSectionHeader
        title="Support Management"
        subtitle="Manage user queries, feedback and complaints"
        icon={LifeBuoy}
        accentClassName="bg-purple-500 text-purple-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(168,85,247,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
      />

      <SupportEncryptionMigration mode="support" context={cryptoContext} />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <div className="border-border bg-card rounded-xl border px-4 py-2 text-xs">
          <span className="text-muted-foreground">Open</span>
          <strong className="text-foreground ml-2">{queueCounts.open}</strong>
        </div>
        <div className="flex items-center rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-2 text-xs text-amber-700 dark:text-amber-300">
          <AlertTriangle size={14} className="mr-2" /> SLA overdue{" "}
          <strong className="ml-2">{queueCounts.overdue}</strong>
        </div>
        <span className="text-muted-foreground text-xs">
          {queueCounts.total} tickets in this queue view
        </span>
        <RoundedSelect
          label="Filter tickets by status"
          value={statusFilter}
          className="ml-auto"
          onChange={(value) => {
            setStatusFilter(value);
            setPageOffset(0);
            setUsers([]);
            setSelectedUserId(null);
          }}
          options={[
            { value: "all", label: "All statuses" },
            ...["open", "in_progress", "waiting_user", "resolved", "closed"].map((status) => ({
              value: status,
              label: status.replaceAll("_", " "),
            })),
          ]}
        />
        <RoundedSelect
          label="Filter by priority"
          value={priorityFilter}
          onChange={(value) => {
            setPriorityFilter(value);
            setPageOffset(0);
            setUsers([]);
            setSelectedUserId(null);
          }}
          options={[
            { value: "all", label: "All priorities" },
            ...["urgent", "high", "normal", "low"].map((priority) => ({
              value: priority,
              label: priority,
            })),
          ]}
        />
        <RoundedSelect
          label="Filter by assignee"
          value={assignmentFilter}
          onChange={(value) => {
            setAssignmentFilter(value);
            setPageOffset(0);
            setUsers([]);
            setSelectedUserId(null);
          }}
          options={[
            { value: "all", label: "All assignees" },
            { value: "mine", label: "Assigned to me" },
            { value: "unassigned", label: "Unassigned" },
          ]}
        />
        <label className="border-border text-foreground flex items-center gap-2 rounded-lg border px-3 py-2 text-xs">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(event) => {
              setOverdueOnly(event.target.checked);
              setPageOffset(0);
              setUsers([]);
              setSelectedUserId(null);
            }}
          />
          SLA overdue only
        </label>
      </div>

      {loadError && (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/35 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-400/25 dark:bg-rose-400/10 dark:text-rose-200"
        >
          <span>{loadError}</span>
          <button
            type="button"
            onClick={() => void loadData()}
            className="rounded-lg border border-red-400/30 px-3 py-1.5 text-xs font-semibold"
          >
            Retry
          </button>
        </div>
      )}

      <div className="mt-4 flex flex-1 flex-col gap-6 overflow-hidden xl:flex-row">
        {/* Users List - Left Side */}
        <div className="theme-panel border-border flex w-full flex-col overflow-hidden rounded-[2rem] border xl:w-80">
          <div className="border-border border-b p-6">
            <div className="relative">
              <Search
                className="text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2"
                size={16}
              />
              <input
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPageOffset(0);
                  setUsers([]);
                  setSelectedUserId(null);
                }}
                placeholder="Search user email..."
                className="border-border bg-background text-foreground placeholder:text-muted-foreground focus:border-primary/50 w-full rounded-xl border py-2.5 pr-4 pl-10 text-xs transition outline-none"
              />
            </div>

          </div>

          <div className="flex-1 space-y-2 overflow-y-auto p-3">
            {loading ? (
              <div className="flex justify-center py-20">
                <Loader2 className="text-primary animate-spin" size={32} />
              </div>
            ) : loadError ? (
              <div className="py-20 text-center text-xs text-rose-800 dark:text-rose-200">
                Support queue unavailable.
              </div>
            ) : filteredUsers.length === 0 ? (
              <div className="text-muted-foreground py-20 text-center text-xs italic">
                No users found.
              </div>
            ) : (
              filteredUsers.map((u) => (
                <button
                  key={u.user_id}
                  onClick={() => setSelectedUserId(u.user_id)}
                  className={`group flex w-full items-center gap-3 rounded-2xl p-3 transition ${
                    selectedUserId === u.user_id
                      ? "bg-primary/10 border-primary/20 border"
                      : "border border-transparent hover:bg-primary/5"
                  }`}
                >
                  <ProfileAvatar
                    avatar={u.avatar}
                    displayName={u.display_name}
                    fallbackLabel={u.email}
                    className="h-10 w-10 rounded-xl"
                  />
                  <div className="min-w-0 flex-1 text-left">
                    <p
                      className={`truncate text-xs font-bold ${selectedUserId === u.user_id ? "text-foreground" : "text-body"}`}
                    >
                      {u.email}
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-[10px]">
                      {u.ticket_count} {u.ticket_count === 1 ? "ticket" : "tickets"}
                    </p>
                  </div>
                  {selectedUserId === u.user_id && (
                    <ChevronRight className="text-primary" size={14} />
                  )}
                </button>
              ))
            )}
            {!loading && hasMoreTickets && (
              <button
                type="button"
                onClick={() => setPageOffset((offset) => offset + 100)}
                className="border-border text-foreground hover:border-primary/40 w-full rounded-lg border px-3 py-2 text-xs font-semibold"
              >
                Load more tickets
              </button>
            )}
          </div>
        </div>

        {/* Tickets View - Right Side */}
        <div className="theme-panel border-border flex flex-1 flex-col overflow-hidden rounded-[2rem] border">
          {selectedUser ? (
            <>
              <div className="border-border bg-surface-2 border-b p-8">
                <h3 className="text-foreground text-lg font-bold">Support history</h3>
                <p className="text-muted-foreground mt-1 text-xs">
                  Tickets for the selected user.
                </p>
              </div>

              <div className="flex-1 space-y-6 overflow-y-auto p-8">
                {selectedUser.latest_tickets.map((ticket) => (
                  <motion.div
                    key={ticket.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="border-border bg-surface-1 overflow-hidden rounded-3xl border"
                  >
                    <div className="p-6">
                      <div className="mb-4 flex items-start justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span
                              className={`rounded-lg border px-2 py-0.5 text-[9px] font-black tracking-tighter uppercase ${
                                ticket.category === "complaint"
                                  ? "border-rose-500/30 bg-rose-50 text-rose-800 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-300"
                                  : ticket.category === "feedback"
                                    ? "border-violet-500/30 bg-violet-50 text-violet-800 dark:border-violet-400/20 dark:bg-violet-400/10 dark:text-violet-300"
                                    : "border-teal-500/30 bg-teal-50 text-teal-800 dark:border-teal-400/20 dark:bg-teal-400/10 dark:text-teal-300"
                              }`}
                            >
                              {ticket.category}
                            </span>
                            <span className="text-muted-foreground font-mono text-[10px]">
                              #{ticket.id.slice(0, 8)}
                            </span>
                          </div>
                          <h4 className="text-foreground text-base font-bold">{ticket.subject}</h4>
                        </div>

                        <div className="flex items-center gap-2">
                          <div
                            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1 text-[10px] font-bold ${
                              ticket.status === "open"
                                ? "border-teal-500/30 bg-teal-50 text-teal-800 dark:border-teal-400/20 dark:bg-teal-400/5 dark:text-teal-300"
                                : ticket.status === "in_progress"
                                  ? "border-amber-500/30 bg-amber-50 text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/5 dark:text-amber-300"
                                  : ticket.status === "resolved"
                                    ? "border-emerald-500/30 bg-emerald-50 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/5 dark:text-emerald-300"
                                    : "border-border text-muted-foreground"
                            }`}
                          >
                            {getStatusIcon(ticket.status)}
                            {ticket.status.replace("_", " ").toUpperCase()}
                          </div>
                        </div>
                      </div>

                      <div className="border-border bg-surface-1 text-body rounded-2xl border p-5 text-sm leading-relaxed">
                        {ticket.description}
                      </div>

                      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
                        <p className="text-muted-foreground text-[10px] font-medium">
                          Submitted on {new Date(ticket.created_at).toLocaleString()}
                        </p>

                        <div className="flex items-center gap-2">
                          <RoundedSelect
                            label="Ticket status"
                            value={ticket.status}
                            disabled={saving}
                            onChange={(status) => void handleUpdateStatus(ticket.id, status)}
                            triggerClassName="min-w-28 px-2 py-1.5 text-[10px]"
                            options={[
                              "open",
                              "in_progress",
                              "waiting_user",
                              "resolved",
                              "closed",
                            ].map((status) => ({
                              value: status,
                              label: status.replaceAll("_", " "),
                            }))}
                          />
                          <button
                            disabled={saving}
                            onClick={() => void assignToMe(ticket.id)}
                            className="border-primary/20 bg-primary/10 text-primary rounded-lg border px-2 py-1.5 text-[10px] font-semibold disabled:opacity-50"
                          >
                            {ticket.assigned_admin_id === user?.id
                              ? "Assigned to me"
                              : "Assign to me"}
                          </button>
                          <RoundedSelect
                            label="Ticket priority"
                            value={ticket.priority ?? "normal"}
                            disabled={saving}
                            onChange={(priority) => void handleUpdatePriority(ticket.id, priority)}
                            triggerClassName="min-w-24 px-2 py-1.5 text-[10px]"
                            options={["low", "normal", "high", "urgent"].map((priority) => ({
                              value: priority,
                              label: priority,
                            }))}
                          />
                          <button
                            onClick={() => {
                              setSelectedTicketId(ticket.id);
                              setReplyDraft("");
                              void loadTicketDetail(ticket.id);
                            }}
                            className="border-primary/20 bg-primary/10 text-primary rounded-lg border px-3 py-1.5 text-[10px] font-bold"
                          >
                            {selectedTicketId === ticket.id
                              ? "Refresh thread"
                              : "Open conversation"}
                          </button>
                        </div>
                      </div>
                      <p className="text-muted-foreground mt-2 text-[10px]">
                        First response due:{" "}
                        {ticket.first_response_due_at
                          ? new Date(ticket.first_response_due_at).toLocaleString()
                          : "Not scheduled"}
                        <span className="mx-2">·</span>
                        Resolution due:{" "}
                        {ticket.resolution_due_at
                          ? new Date(ticket.resolution_due_at).toLocaleString()
                          : "Not scheduled"}
                      </p>
                      <AnimatePresence initial={false}>
                        {selectedTicketId === ticket.id && (
                          <motion.div
                            key={`admin-support-thread-${ticket.id}`}
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.2, ease: "easeInOut" }}
                            className="overflow-hidden"
                          >
                            <div className="border-border mt-5 space-y-3 border-t pt-4">
                              {(ticketDetails[ticket.id]?.attachments ?? []).length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {(ticketDetails[ticket.id]?.attachments ?? []).map(
                                    (attachment) => (
                                      <button
                                        key={attachment.id}
                                        type="button"
                                        onClick={() =>
                                          void downloadAttachment(
                                            attachment.download_url,
                                            attachment.filename,
                                            Boolean(attachment.is_encrypted),
                                            attachment.encrypted_metadata,
                                          )
                                        }
                                        className="border-border bg-surface-1 text-body hover:border-primary/40 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
                                      >
                                        <Paperclip size={13} /> {attachment.filename}{" "}
                                        <span className="text-muted-foreground">
                                          {(attachment.size_bytes / 1024).toFixed(0)} KB
                                        </span>
                                      </button>
                                    ),
                                  )}
                                </div>
                              )}
                              {(ticketDetails[ticket.id]?.attachments ?? []).some(
                                (attachment) => attachment.is_encrypted,
                              ) && (
                                <p className="text-amber-800 dark:text-amber-300 text-xs leading-5">
                                  Encrypted attachments cannot be scanned by the VPS. Download only files you trust.
                                </p>
                              )}
                              <div className="max-h-72 space-y-2 overflow-y-auto">
                                {(ticketDetails[ticket.id]?.messages ?? []).map((message) => {
                                  const participant = ticketDetails[ticket.id]?.participants?.find(
                                    (candidate) => candidate.ref === message.author_ref,
                                  );
                                  const authorLabel = message.is_internal
                                    ? "Internal note"
                                    : message.author_role === "admin"
                                      ? "Support team"
                                      : message.author_role === "user"
                                        ? "User"
                                        : "Status update";
                                  return (
                                    <article
                                      key={message.id}
                                      className={`rounded-xl border p-3 ${message.is_internal ? "border-amber-500/35 bg-amber-50 text-amber-950 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-100" : "border-border bg-surface-1 text-foreground"}`}
                                    >
                                      <div className="flex items-start gap-3">
                                        <ProfileAvatar
                                          avatar={participant?.avatar}
                                          displayName={participant?.display_name}
                                          fallbackLabel={authorLabel}
                                          className="h-8 w-8 rounded-lg"
                                        />
                                        <div className="min-w-0 flex-1">
                                          <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-[10px]">
                                            <span className="text-foreground font-semibold">
                                              {participant?.display_name || authorLabel}
                                            </span>
                                            <time>{new Date(message.created_at).toLocaleString()}</time>
                                          </div>
                                          <p className="text-body mt-1 text-xs whitespace-pre-wrap">
                                            {message.body}
                                          </p>
                                        </div>
                                      </div>
                                    </article>
                                  );
                                })}
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <RoundedSelect
                                  label="Reply visibility"
                                  value={visibility}
                                  onChange={(value) =>
                                    setVisibility(value as "public" | "internal")
                                  }
                                  triggerClassName="px-2 py-2 text-[10px]"
                                  options={[
                                    { value: "public", label: "Reply to user" },
                                    { value: "internal", label: "Internal note" },
                                  ]}
                                />
                                <input
                                  value={replyDraft}
                                  maxLength={10000}
                                  onChange={(event) => setReplyDraft(event.target.value)}
                                  placeholder={
                                    visibility === "public"
                                      ? "Write a reply…"
                                      : "Write a private note…"
                                  }
                                  className="border-border bg-background text-foreground placeholder:text-muted-foreground min-w-40 flex-1 rounded-lg border px-3 py-2 text-xs"
                                />
                                <button
                                  disabled={saving || !replyDraft.trim()}
                                  onClick={() => void sendReply(ticket.id)}
                                  className="bg-primary rounded-lg px-3 py-2 text-xs font-bold text-black disabled:opacity-50"
                                >
                                  Send
                                </button>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </motion.div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center p-20 text-center">
              <div className="theme-chip text-primary mb-6 flex h-24 w-24 items-center justify-center rounded-3xl">
                <MessageSquare size={48} />
              </div>
              <h3 className="text-foreground mb-2 text-xl font-bold">No User Selected</h3>
              <p className="text-muted-foreground max-w-md">
                Select a user from the left panel to view their support history and manage tickets.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AdminSupportPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full w-full items-center justify-center">
          <Loader2 className="text-primary animate-spin" size={48} />
        </div>
      }
    >
      <SupportContent />
    </Suspense>
  );
}
