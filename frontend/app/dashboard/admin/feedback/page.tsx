"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";

import {
  MessageSquare,
  Plus,
  Sparkles,
  Calendar,
  Search,
  AlertCircle,
  Trophy,
  Star,
  Loader2,
} from "lucide-react";
import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import AverQelLoading from "@/app/components/ui/AverQelLoading";
import ProfileAvatar from "@/app/components/profile/ProfileAvatar";
import RoundedSelect from "@/app/components/ui/RoundedSelect";
import { fetchWithAuth } from "@/lib/api";
import { useSupportEncryption } from "@/app/dashboard/support/SupportEncryptionGate";
import SupportEncryptionMigration from "@/app/dashboard/admin/SupportEncryptionMigration";
import {
  decryptSupportPayload,
  encryptSupportPayload,
  SupportPublicKey,
} from "@/lib/supportEncryption";

interface Submission {
  id: string;
  subject: string;
  content: string;
  category: string;
  created_at: string;
  status: string;
  updated_at?: string;
  encrypted_payload?: string | null;
  recipient_public_key?: SupportPublicKey | null;
  messages?: Array<{
    id: string;
    author_ref?: string | null;
    author_role: string;
    kind: string;
    body: string;
    encrypted_payload?: string | null;
    is_internal: boolean;
    created_at: string;
  }>;
  participants?: ConversationParticipant[];
}

interface ConversationParticipant {
  ref: string;
  display_name?: string | null;
  avatar?: string | null;
}

async function decryptSubmission(
  item: Submission,
  privateKey: CryptoKey,
  keyId: string,
): Promise<Submission> {
  const content = item.encrypted_payload
    ? await decryptSupportPayload<{ subject: string; content: string }>(
        item.encrypted_payload,
        privateKey,
        keyId,
      )
    : null;
  const messages = await Promise.all(
    (item.messages ?? []).map(async (message) =>
      message.encrypted_payload
        ? {
            ...message,
            ...(await decryptSupportPayload<{ body: string }>(
              message.encrypted_payload,
              privateKey,
              keyId,
            )),
          }
        : message,
    ),
  );
  return { ...item, ...(content ?? {}), messages };
}

interface Campaign {
  id: string;
  title: string;
  description: string;
  is_active: boolean;
  created_at: string;
}

function FeedbackFilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return <RoundedSelect label={label} value={value} options={options} onChange={onChange} />;
}

export default function AdminFeedbackPage() {
  const encryption = useSupportEncryption("admin");
  const cryptoContext = encryption.context;
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateCampaign, setShowCreateCampaign] = useState(false);
  const [newCampaign, setNewCampaign] = useState({ title: "", description: "" });
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reply, setReply] = useState("");
  const [visibility, setVisibility] = useState<"public" | "internal">("public");
  const [saving, setSaving] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [loadingThread, setLoadingThread] = useState(false);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const detailRequest = useRef(0);

  const fetchData = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!options?.silent) setRefreshing(true);
      try {
        const [subRes, campRes] = await Promise.all([
          fetchWithAuth("/app-feedback/admin/submissions"),
          fetchWithAuth("/app-feedback/campaigns"),
        ]);

        if (!subRes.ok) {
          const reason =
            subRes.status === 403
              ? "Your account cannot review feedback. Use an allowlisted platform-administrator account."
              : `Could not load feedback submissions (${subRes.status}).`;
          throw new Error(reason);
        }
        if (!cryptoContext) throw new Error("Support encryption is locked.");
        const rows = (await subRes.json()) as Submission[];
        const queueRows = await Promise.all(
          rows.map((row) => decryptSubmission(row, cryptoContext.privateKey, cryptoContext.keyId)),
        );
        setSubmissions((current) =>
          queueRows.map((row) => {
            const loadedDetail = current.find((item) => item.id === row.id);
            return loadedDetail?.messages ? { ...row, messages: loadedDetail.messages } : row;
          }),
        );
        setQueueError(null);
        if (campRes.ok) setCampaigns(await campRes.json());
      } catch (err) {
        console.error("Failed to fetch admin data", err);
        setQueueError(err instanceof Error ? err.message : "Could not load feedback submissions.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [cryptoContext],
  );

  useEffect(() => {
    if (!encryption.ready || !cryptoContext) return;
    queueMicrotask(() => void fetchData());
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void fetchData({ silent: true });
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [fetchData, encryption.ready, cryptoContext]);

  const loadDetail = useCallback(
    async (id: string) => {
      setSelectedId(id);
      setThreadError(null);
      setLoadingThread(true);
      const requestId = ++detailRequest.current;
      try {
        const res = await fetchWithAuth(`/app-feedback/admin/submissions/${id}`);
        if (!res.ok) throw new Error(`Could not load feedback (${res.status})`);
        const detail = (await res.json()) as Submission;
        if (requestId === detailRequest.current) {
          if (!cryptoContext) throw new Error("Support encryption is locked.");
          const decrypted = await decryptSubmission(
            detail,
            cryptoContext.privateKey,
            cryptoContext.keyId,
          );
          setSubmissions((current) => [decrypted, ...current.filter((item) => item.id !== id)]);
        }
      } catch (err) {
        console.error(err);
        if (requestId === detailRequest.current) {
          setThreadError("Could not load this conversation. Check access or try again.");
          toast.error("Could not load this feedback thread.");
        }
      } finally {
        if (requestId === detailRequest.current) setLoadingThread(false);
      }
    },
    [cryptoContext],
  );

  useEffect(() => {
    if (!encryption.ready || !cryptoContext) return;
    const id = new URLSearchParams(window.location.search).get("submission");
    if (id) queueMicrotask(() => void loadDetail(id));
  }, [encryption.ready, cryptoContext, loadDetail]);

  async function updateStatus(item: Submission, status: string) {
    setSaving(true);
    try {
      const res = await fetchWithAuth(`/app-feedback/admin/submissions/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(`Status update failed (${res.status})`);
      await fetchData();
      if (selectedId === item.id) await loadDetail(item.id);
      toast.success("Feedback status updated.");
    } catch (err) {
      console.error(err);
      toast.error("Could not update feedback status.");
    } finally {
      setSaving(false);
    }
  }

  async function sendReply() {
    if (!selectedId || !reply.trim()) return;
    if (!cryptoContext) return;
    setSaving(true);
    try {
      const selected = submissions.find((item) => item.id === selectedId);
      if (!selected) throw new Error("Feedback details are not loaded.");
      const recipients =
        visibility === "internal"
          ? [cryptoContext.ownPublicKey]
          : selected.recipient_public_key
            ? [cryptoContext.ownPublicKey, selected.recipient_public_key]
            : null;
      if (!recipients) throw new Error("The user has not initialized support encryption.");
      const res = await fetchWithAuth(`/app-feedback/admin/submissions/${selectedId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          encrypted_payload: await encryptSupportPayload({ body: reply.trim() }, recipients),
          visibility,
        }),
      });
      if (!res.ok) throw new Error(`Reply failed (${res.status})`);
      const detail = await decryptSubmission(
        (await res.json()) as Submission,
        cryptoContext.privateKey,
        cryptoContext.keyId,
      );
      setSubmissions((current) => current.map((item) => (item.id === detail.id ? detail : item)));
      setReply("");
      toast.success(visibility === "public" ? "Reply sent to the user." : "Internal note saved.");
    } catch (err) {
      console.error(err);
      toast.error("Could not send this message.");
    } finally {
      setSaving(false);
    }
  }

  const visibleSubmissions = submissions.filter(
    (item) =>
      (!statusFilter || item.status === statusFilter) &&
      (!categoryFilter || item.category === categoryFilter) &&
      (!search || `${item.subject} ${item.content}`.toLowerCase().includes(search.toLowerCase())),
  );
  const selectedSubmission = submissions.find((item) => item.id === selectedId);

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const res = await fetchWithAuth("/app-feedback/admin/campaigns", {
        method: "POST",
        body: JSON.stringify(newCampaign),
      });
      if (!res.ok) throw new Error(`Campaign creation failed (${res.status})`);
      setShowCreateCampaign(false);
      setNewCampaign({ title: "", description: "" });
      await fetchData();
      toast.success("Feedback campaign is now active for users.");
    } catch (err) {
      console.error("Failed to create campaign", err);
      toast.error("Could not launch the feedback campaign. Check your access and try again.");
    } finally {
      setCreating(false);
    }
  };

  const getCategoryStyles = (category: string) => {
    switch (category) {
      case "bug":
        return {
          icon: <AlertCircle size={14} />,
          color: "border border-rose-500/25 bg-rose-50 text-rose-800 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-300",
        };
      case "achievement":
        return {
          icon: <Trophy size={14} />,
          color: "border border-emerald-500/25 bg-emerald-50 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300",
        };
      case "ux_improvement":
        return {
          icon: <Star size={14} />,
          color: "border border-violet-500/25 bg-violet-50 text-violet-800 dark:border-violet-400/20 dark:bg-violet-400/10 dark:text-violet-300",
        };
      default:
        return {
          icon: <Sparkles size={14} />,
          color: "border border-amber-500/25 bg-amber-50 text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-300",
        };
    }
  };

  if (!encryption.ready || !cryptoContext) return encryption.panel;

  if (loading) {
    return (
      <div className="dashboard-theme-scope space-y-8">
        <DashboardSectionHeader
          title="Feedback Center"
          subtitle="Manage User Engagement And Feedback Requests"
          icon={Sparkles}
          accentClassName="bg-amber-500 text-amber-500"
          accentGlowClassName="shadow-[0_0_20px_rgba(245,158,11,0.4)]"
          backHref="/dashboard"
          backLabel="Back To Dashboard"
        />
        <AverQelLoading label="Loading feedback…" size="section" className="min-h-[60vh]" />
      </div>
    );
  }

  return (
    <div className="dashboard-theme-scope space-y-10">
      <DashboardSectionHeader
        title="Feedback Center"
        subtitle="Manage User Engagement And Feedback Requests"
        icon={Sparkles}
        accentClassName="bg-amber-500 text-amber-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(245,158,11,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
        actions={
          <button
            onClick={() => setShowCreateCampaign(true)}
            className="bg-primary text-primary-foreground shadow-primary/20 flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold shadow-lg transition-all hover:scale-[1.02] active:scale-98"
          >
            <Plus size={18} />
            Launch Campaign
          </button>
        }
      />

      <SupportEncryptionMigration mode="feedback" context={cryptoContext} />

      <aside className="border-border bg-surface-1 text-muted-foreground rounded-2xl border px-4 py-3 text-sm">
        New and migrated feedback is decrypted in this browser for the submitter and the allowlisted
        platform administrator. Other users and legacy manager roles cannot read it. Replies stay in
        the encrypted in-app thread.
      </aside>

      <div className="grid grid-cols-1 gap-10 lg:grid-cols-4">
        {/* Campaigns Column */}
        <div className="space-y-6 lg:col-span-1">
          <h2 className="text-muted-foreground px-1 text-xs font-bold tracking-widest uppercase">
            Active Campaigns
          </h2>
          <div className="space-y-4">
            {campaigns.map((c) => (
              <div key={c.id} className="theme-panel-muted rounded-2xl border border-border p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-primary text-[10px] font-bold uppercase">Active</span>
                </div>
                <h3 className="text-foreground text-sm font-bold">{c.title}</h3>
                <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">{c.description}</p>
                <div className="text-muted-foreground mt-4 flex items-center gap-4 text-[10px]">
                  <span className="flex items-center gap-1">
                    <Calendar size={12} /> Created {new Date(c.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
            {campaigns.length === 0 && (
              <p className="text-muted-foreground rounded-2xl border border-dashed border-border py-10 text-center text-sm">
                No active campaigns
              </p>
            )}
          </div>
        </div>

        {/* Submissions Column */}
        <div className="space-y-6 lg:col-span-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-muted-foreground text-xs font-bold tracking-widest uppercase">
              User Submissions
            </h2>
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => void fetchData()}
                disabled={refreshing}
                className="border-border text-foreground rounded-lg border px-3 py-2 text-xs font-semibold disabled:opacity-50"
              >
                {refreshing ? "Refreshing…" : "Refresh"}
              </button>
              <div className="relative">
                <Search
                  size={14}
                  className="text-muted-foreground absolute top-1/2 left-3 -translate-y-1/2"
                />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search feedback..."
                  className="focus:border-primary/50 border-border bg-background text-foreground rounded-xl border py-1.5 pr-4 pl-9 text-xs focus:outline-none"
                />
              </div>
              <FeedbackFilterSelect
                label="Filter feedback status"
                value={statusFilter}
                onChange={setStatusFilter}
                options={[
                  { value: "", label: "All statuses" },
                  ...["new", "triaged", "planned", "in_progress", "completed", "declined"].map(
                    (status) => ({
                      value: status,
                      label: status.replaceAll("_", " "),
                    }),
                  ),
                ]}
              />
              <FeedbackFilterSelect
                label="Filter feedback category"
                value={categoryFilter}
                onChange={setCategoryFilter}
                options={[
                  { value: "", label: "All categories" },
                  ...[...new Set(submissions.map((item) => item.category))].map((category) => ({
                    value: category,
                    label: category.replaceAll("_", " "),
                  })),
                ]}
              />
            </div>
          </div>

          {queueError && (
            <div
              role="alert"
              className="text-foreground flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/30 bg-rose-500/5 px-4 py-3 text-sm"
            >
              <span>{queueError}</span>
              <button
                type="button"
                onClick={() => void fetchData()}
                className="text-primary font-semibold underline underline-offset-2"
              >
                Try again
              </button>
            </div>
          )}

          <div className="space-y-4">
            {visibleSubmissions.map((s) => {
              const styles = getCategoryStyles(s.category);
              return (
                <motion.div
                  key={s.id}
                  layout
                  className="theme-panel group relative rounded-3xl border border-border p-6 transition-all hover:border-primary/40 hover:bg-primary/5"
                >
                  <div className="flex items-start justify-between gap-6">
                    <div className="flex-1 space-y-4">
                      <div className="flex items-center gap-3">
                        <span
                          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-bold tracking-wider uppercase ${styles.color}`}
                        >
                          {styles.icon}
                          {s.category.replace("_", " ")}
                        </span>
                        <span className="text-muted-foreground text-xs">
                          {new Date(s.created_at).toLocaleDateString()}
                        </span>
                        <span className="text-foreground rounded-full border border-border bg-surface-2 px-2 py-1 text-[10px] font-medium uppercase">
                          {s.status?.replace("_", " ") ?? "new"}
                        </span>
                      </div>
                      <div>
                        <h3 className="text-foreground text-lg font-bold">{s.subject}</h3>
                        <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
                          {s.content}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <RoundedSelect
                        label={`Update status for ${s.subject}`}
                        value={s.status ?? "new"}
                        disabled={saving}
                        onChange={(status) => void updateStatus(s, status)}
                        options={[
                          "new",
                          "triaged",
                          "planned",
                          "in_progress",
                          "completed",
                          "declined",
                        ].map((status) => ({ value: status, label: status.replaceAll("_", " ") }))}
                      />
                      <button
                        onClick={() => void loadDetail(s.id)}
                        className="border-primary/20 bg-primary/10 text-primary hover:bg-primary/20 rounded-lg border px-3 py-2 text-xs font-semibold"
                      >
                        Open thread
                      </button>
                    </div>
                  </div>
                </motion.div>
              );
            })}
            {visibleSubmissions.length === 0 && (
              <div className="border-border bg-surface-1 flex flex-col items-center justify-center rounded-3xl border border-dashed py-32 text-center">
                <div className="theme-chip text-primary mb-4 rounded-full p-4">
                  <MessageSquare size={32} />
                </div>
                <h3 className="text-foreground font-bold">
                  {submissions.length ? "No matching feedback" : "No feedback yet"}
                </h3>
                <p className="text-muted-foreground mt-2 max-w-xs text-sm">
                  Start a campaign to encourage users to share their thoughts and experiences.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {selectedId && (
              <motion.div
                key="feedback-conversation-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.16 }}
                className="fixed inset-0 z-[70] flex justify-end bg-slate-950/15"
                style={{
                  position: "fixed",
                  inset: 0,
                  zIndex: 1000,
                  display: "flex",
                  justifyContent: "flex-end",
                }}
                onMouseDown={(event) => {
                  if (event.target === event.currentTarget) setSelectedId(null);
                }}
              >
                <motion.section
                  initial={{ x: 28, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: 28, opacity: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                  className="border-border bg-background flex min-h-0 w-full max-w-2xl flex-col overflow-hidden border-l p-5 shadow-2xl sm:p-6"
                  style={{ height: "100dvh", minHeight: 0, flex: "0 1 42rem" }}
                  aria-label="Feedback conversation"
                >
                  <div className="border-border flex shrink-0 items-start justify-between gap-4 border-b pb-4">
                    <div>
                      <p className="text-muted-foreground text-xs tracking-widest uppercase">
                        Feedback conversation
                      </p>
                      <h2 className="text-foreground mt-1 text-lg font-bold break-words">
                        {selectedSubmission?.subject ?? (
                          <AverQelLoading size="inline" label="Loading feedback subject" />
                        )}
                      </h2>
                      {selectedSubmission && (
                        <div className="text-muted-foreground mt-3 flex items-center gap-2 text-xs">
                          <ProfileAvatar
                            avatar={selectedSubmission.participants?.[0]?.avatar}
                            displayName={selectedSubmission.participants?.[0]?.display_name}
                            fallbackLabel="Feedback submitter"
                            className="h-8 w-8 rounded-full"
                          />
                          <span>
                            Submitted by {selectedSubmission.participants?.[0]?.display_name || "user"}
                          </span>
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => void loadDetail(selectedId)}
                      disabled={loadingThread}
                      className="border-border text-foreground rounded-lg border px-3 py-2 text-xs disabled:opacity-50"
                    >
                      {loadingThread ? (
                        <AverQelLoading size="inline" label="Loading conversation" />
                      ) : (
                        "Refresh conversation"
                      )}
                    </button>
                    <button
                      onClick={() => setSelectedId(null)}
                      className="border-border text-foreground hover:bg-foreground/5 shrink-0 rounded-lg border px-3 py-2 text-xs"
                    >
                      Close
                    </button>
                  </div>
                  <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain py-4">
                    {loadingThread && (
                      <AverQelLoading
                        label="Loading conversation…"
                        size="compact"
                        className="justify-start py-3"
                      />
                    )}
                    {threadError && (
                      <div
                        role="alert"
                        className="text-foreground rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-sm"
                      >
                        {threadError}
                        <button
                          type="button"
                          onClick={() => void loadDetail(selectedId)}
                          className="text-primary ml-2 font-semibold underline underline-offset-2"
                        >
                          Retry
                        </button>
                      </div>
                    )}
                    {(selectedSubmission?.messages ?? []).map((message) => {
                      const participant = selectedSubmission?.participants?.find(
                        (candidate) => candidate.ref === message.author_ref,
                      );
                      const authorLabel = message.is_internal
                        ? "Internal note"
                        : message.kind === "status_changed"
                          ? "Status update"
                          : message.author_role === "admin"
                            ? "Support team"
                            : "User";
                      return (
                        <article
                          key={message.id}
                          className={`min-w-0 rounded-xl border p-4 ${message.is_internal ? "border-amber-500/35 bg-amber-50 text-amber-950 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-100" : "border-border bg-surface-1 text-foreground"}`}
                        >
                          <div className="mb-2 flex items-start gap-3">
                            <ProfileAvatar
                              avatar={participant?.avatar}
                              displayName={participant?.display_name}
                              fallbackLabel={authorLabel}
                              className="h-9 w-9 rounded-xl"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="text-foreground text-xs font-semibold">
                                  {participant?.display_name || authorLabel}
                                </span>
                                <time className="text-muted-foreground text-[10px]">
                                  {new Date(message.created_at).toLocaleString()}
                                </time>
                              </div>
                              {message.is_internal && (
                                <span className="mt-1 inline-flex rounded-full bg-amber-200 px-2 py-0.5 text-[9px] font-bold tracking-wide text-amber-950 uppercase dark:bg-amber-300/15 dark:text-amber-200">
                                  Internal note
                                </span>
                              )}
                            </div>
                          </div>
                          <p className="text-sm leading-relaxed [overflow-wrap:anywhere] break-words whitespace-pre-wrap">
                            {message.body}
                          </p>
                        </article>
                      );
                    })}
                    {!loadingThread &&
                      !threadError &&
                      !selectedSubmission?.messages?.length && (
                        <p className="text-muted-foreground py-10 text-center text-sm">
                          No replies yet. Send a public response or add an internal note.
                        </p>
                      )}
                  </div>
                  <form
                    className="border-border bg-background shrink-0 space-y-3 border-t pt-4"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void sendReply();
                    }}
                  >
                    <RoundedSelect
                      label="Reply visibility"
                      value={visibility}
                      onChange={(next) => setVisibility(next as "public" | "internal")}
                      options={[
                        { value: "public", label: "Reply to user" },
                        { value: "internal", label: "Internal note" },
                      ]}
                    />
                    <textarea
                      id="feedback-reply-body"
                      aria-label={
                        visibility === "public"
                          ? "Write a reply visible to the user"
                          : "Write a private internal note"
                      }
                      value={reply}
                      onChange={(event) => setReply(event.target.value)}
                      maxLength={10000}
                      rows={4}
                      placeholder={
                        visibility === "public"
                          ? "Write a reply visible to the user…"
                          : "Write a private internal note…"
                      }
                      className="border-border bg-background text-foreground placeholder:text-muted-foreground focus:border-primary/50 min-h-28 w-full resize-y rounded-xl border p-3 text-sm outline-none"
                    />
                    <button
                      type="submit"
                      disabled={saving || !reply.trim()}
                      className="bg-primary text-primary-foreground rounded-xl px-4 py-2 text-sm font-bold disabled:opacity-50"
                    >
                      {saving
                        ? "Saving…"
                        : visibility === "public"
                          ? "Send reply"
                          : "Add internal note"}
                    </button>
                  </form>
                </motion.section>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}

      {/* Create Campaign Modal */}
      {typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {showCreateCampaign && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onMouseDown={(event) => {
                  if (event.target === event.currentTarget) setShowCreateCampaign(false);
                }}
                className="fixed inset-0 z-[1100] flex items-start justify-center overflow-y-auto bg-transparent p-4 sm:items-center sm:p-6"
                style={{ position: "fixed", inset: 0, zIndex: 1100 }}
              >
                <motion.section
                  initial={{ y: 8, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: 8, opacity: 0 }}
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="feedback-campaign-title"
                  className="border-border bg-background text-foreground my-auto max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-2xl border p-5 shadow-xl sm:p-7"
                >
                  <h2
                    id="feedback-campaign-title"
                    className="text-foreground mb-2 text-2xl font-bold"
                  >
                    Launch New Campaign
                  </h2>
                  <p className="text-muted-foreground mb-6 text-sm">
                    Request specific feedback from your users about features or improvements.
                  </p>

                  <form onSubmit={handleCreateCampaign} className="space-y-5">
                    <div className="space-y-2">
                      <label
                        htmlFor="feedback-campaign-name"
                        className="text-muted-foreground text-[10px] font-bold tracking-[0.2em] uppercase"
                      >
                        Campaign Title
                      </label>
                      <input
                        id="feedback-campaign-name"
                        required
                        value={newCampaign.title}
                        onChange={(e) => setNewCampaign({ ...newCampaign, title: e.target.value })}
                        placeholder="e.g. New DeepSpace Experience"
                        className="focus:border-primary/50 border-border bg-surface-1 text-foreground w-full rounded-xl border px-4 py-3 transition-all focus:outline-none"
                      />
                    </div>

                    <div className="space-y-2">
                      <label
                        htmlFor="feedback-campaign-details"
                        className="text-muted-foreground text-[10px] font-bold tracking-[0.2em] uppercase"
                      >
                        Request Details
                      </label>
                      <textarea
                        id="feedback-campaign-details"
                        required
                        rows={4}
                        value={newCampaign.description}
                        onChange={(e) =>
                          setNewCampaign({ ...newCampaign, description: e.target.value })
                        }
                        placeholder="What specific input do you need from users?"
                        className="focus:border-primary/50 border-border bg-surface-1 text-foreground w-full resize-y rounded-xl border px-4 py-3 transition-all focus:outline-none"
                      />
                    </div>

                    <div className="flex flex-col-reverse gap-3 pt-1 sm:flex-row sm:justify-end">
                      <button
                        type="button"
                        onClick={() => setShowCreateCampaign(false)}
                        className="border-border text-foreground hover:bg-surface-1 rounded-xl border px-5 py-3 text-sm font-semibold transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        disabled={creating}
                        className="bg-primary text-primary-foreground rounded-xl px-5 py-3 text-sm font-bold transition-opacity disabled:opacity-50"
                      >
                        {creating ? (
                          <Loader2 className="mx-auto animate-spin" size={18} />
                        ) : (
                          "Launch Now"
                        )}
                      </button>
                    </div>
                  </form>
                </motion.section>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </div>
  );
}
