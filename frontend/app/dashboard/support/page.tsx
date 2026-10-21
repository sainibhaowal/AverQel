"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import {
  Send,
  History,
  Loader2,
  AlertCircle,
  HelpCircle,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  LifeBuoy,
  Paperclip,
  UploadCloud,
} from "lucide-react";

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";
import ProfileAvatar from "@/app/components/profile/ProfileAvatar";
import RoundedSelect from "@/app/components/ui/RoundedSelect";
import { fetchWithAuth } from "@/lib/api";
import { useAuth } from "@/app/context/AuthContext";
import { useSupportEncryption } from "@/app/dashboard/support/SupportEncryptionGate";
import {
  decryptSupportAttachment,
  decryptSupportPayload,
  encryptSupportAttachment,
  encryptSupportPayload,
} from "@/lib/supportEncryption";

interface Ticket {
  id: string;
  subject: string;
  description: string;
  category: string;
  status: string;
  priority: string;
  created_at: string;
  updated_at: string;
  encrypted_payload?: string | null;
}

interface TicketMessage {
  id: string;
  author_ref?: string | null;
  author_role: string;
  kind: string;
  body: string;
  encrypted_payload?: string | null;
  created_at: string;
}

interface ConversationParticipant {
  ref: string;
  display_name?: string | null;
  avatar?: string | null;
}

interface TicketDetail extends Ticket {
  messages: TicketMessage[];
  participants?: ConversationParticipant[];
  attachments?: Array<{
    id: string;
    filename: string;
    size_bytes: number;
    download_url: string;
    is_encrypted?: boolean;
    encrypted_metadata?: string | null;
  }>;
}

async function decryptTicket<T extends Ticket>(
  ticket: T,
  privateKey: CryptoKey,
  keyId: string,
): Promise<T> {
  if (!ticket.encrypted_payload) return ticket;
  const content = await decryptSupportPayload<{ subject: string; description: string }>(
    ticket.encrypted_payload,
    privateKey,
    keyId,
  );
  return { ...ticket, ...content };
}

const supportCategories = [
  ["query", "General question"],
  ["technical_issue", "Technical issue"],
  ["account_access", "Account or access"],
  ["billing_plan", "Billing or plan"],
  ["documents_storage", "Documents or storage"],
  ["query_results", "Query results"],
  ["deepspace_agent", "DeepSpace agent"],
  ["provider_integrations", "Providers or integrations"],
  ["security_privacy", "Security or privacy"],
  ["feature_request", "Feature request"],
  ["complaint", "Complaint"],
  ["other", "Other"],
] as const;

export default function SupportPage() {
  const { user, userDisabled } = useAuth();
  const encryption = useSupportEncryption("user");
  const cryptoContext = encryption.context;
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<string>("query");
  const [submitting, setSubmitting] = useState(false);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [ticketListError, setTicketListError] = useState<string | null>(null);
  const [ticketDetailErrors, setTicketDetailErrors] = useState<Record<string, string>>({});
  const [expandedTicket, setExpandedTicket] = useState<string | null>(null);
  const [ticketDetails, setTicketDetails] = useState<Record<string, TicketDetail>>({});
  const [replyDraft, setReplyDraft] = useState("");
  const [sendingReply, setSendingReply] = useState(false);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);

  const uploadAttachment = async (ticketId: string, file?: File) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      toast.error("Attachments are limited to 5 MiB.");
      return;
    }
    setUploadingAttachment(true);
    try {
      const form = new FormData();
      if (!cryptoContext) throw new Error("Unlock support encryption before uploading.");
      const encrypted = await encryptSupportAttachment(file, [
        cryptoContext.ownPublicKey,
        cryptoContext.adminPublicKey,
      ]);
      form.append("file", encrypted.encryptedFile, "encrypted.bin");
      form.append("encrypted_metadata", encrypted.encryptedMetadata);
      const response = await fetchWithAuth(`/support/tickets/${ticketId}/attachments`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(`Upload failed (${response.status})`);
      await loadTicketDetail(ticketId);
      toast.success("Attachment uploaded securely.");
    } catch (error) {
      console.error(error);
      toast.error("Could not upload this attachment.");
    } finally {
      setUploadingAttachment(false);
    }
  };

  const openAttachment = async (
    url: string,
    filename: string,
    isEncrypted = false,
    encryptedMetadata?: string | null,
  ) => {
    try {
      if (!cryptoContext) throw new Error("Unlock support encryption before downloading.");
      const response = await fetchWithAuth(url);
      if (!response.ok) throw new Error(`Download failed (${response.status})`);
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
      toast.error("Could not download this attachment.");
    }
  };

  const loadTicketDetail = async (ticketId: string) => {
    try {
      const res = await fetchWithAuth(`/support/tickets/${ticketId}`);
      if (!res.ok) throw new Error(`Ticket conversation could not be loaded (${res.status}).`);
      const detail = (await res.json()) as TicketDetail;
      if (!cryptoContext) throw new Error("Support encryption is locked.");
      const decryptedTicket = await decryptTicket(
        detail,
        cryptoContext.privateKey,
        cryptoContext.keyId,
      );
      const decryptedMessages = await Promise.all(
        detail.messages.map(async (message) => {
          if (!message.encrypted_payload) return message;
          const content = await decryptSupportPayload<{ body: string }>(
            message.encrypted_payload,
            cryptoContext.privateKey,
            cryptoContext.keyId,
          );
          return { ...message, ...content };
        }),
      );
      setTicketDetails((current) => ({
        ...current,
        [ticketId]: { ...decryptedTicket, messages: decryptedMessages },
      }));
      setTicketDetailErrors((current) => {
        const next = { ...current };
        delete next[ticketId];
        return next;
      });
    } catch (err) {
      console.error("Failed to load ticket conversation", err);
      setTicketDetailErrors((current) => ({
        ...current,
        [ticketId]: "Could not load this ticket conversation. Try again.",
      }));
    }
  };

  const handleReply = async (ticketId: string) => {
    if (!replyDraft.trim()) return;
    setSendingReply(true);
    try {
      const res = await fetchWithAuth(`/support/tickets/${ticketId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          encrypted_payload: await encryptSupportPayload({ body: replyDraft.trim() }, [
            cryptoContext!.ownPublicKey,
            cryptoContext!.adminPublicKey,
          ]),
        }),
      });
      if (!res.ok) throw new Error(`Reply failed (${res.status})`);
      const detail = (await res.json()) as TicketDetail;
      if (!cryptoContext) throw new Error("Support encryption is locked.");
      const decryptedTicket = await decryptTicket(
        detail,
        cryptoContext.privateKey,
        cryptoContext.keyId,
      );
      const decryptedMessages = await Promise.all(
        detail.messages.map(async (message) => {
          if (!message.encrypted_payload) return message;
          return {
            ...message,
            ...(await decryptSupportPayload<{ body: string }>(
              message.encrypted_payload,
              cryptoContext.privateKey,
              cryptoContext.keyId,
            )),
          };
        }),
      );
      const decryptedDetail = { ...decryptedTicket, messages: decryptedMessages };
      setTicketDetails((current) => ({ ...current, [ticketId]: decryptedDetail }));
      setTickets((current) =>
        current.map((ticket) => (ticket.id === detail.id ? decryptedDetail : ticket)),
      );
      setReplyDraft("");
      toast.success("Reply sent.");
    } catch (err) {
      console.error(err);
      toast.error("Could not send your reply. Please try again.");
    } finally {
      setSendingReply(false);
    }
  };

  const loadTickets = async () => {
    try {
      const res = await fetchWithAuth("/support/tickets");
      if (!res.ok) throw new Error(`Ticket history could not be loaded (${res.status}).`);
      if (!cryptoContext) throw new Error("Support encryption is locked.");
      const rows = (await res.json()) as Ticket[];
      setTickets(
        await Promise.all(
          rows.map((ticket) =>
            decryptTicket(ticket, cryptoContext.privateKey, cryptoContext.keyId),
          ),
        ),
      );
      setTicketListError(null);
    } catch (err) {
      console.error(err);
      setTicketListError(
        "Your ticket history could not be loaded. Check your connection and retry.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!encryption.ready || !cryptoContext) return;
    queueMicrotask(() => void loadTickets());
  }, [cryptoContext, encryption.ready]);

  useEffect(() => {
    if (!encryption.ready || !cryptoContext) return;
    const ticketId = new URLSearchParams(window.location.search).get("ticket");
    if (ticketId) {
      queueMicrotask(() => {
        setExpandedTicket(ticketId);
        void loadTicketDetail(ticketId);
      });
    }
  }, [cryptoContext, encryption.ready]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !description.trim()) {
      toast.error("Please fill in all fields.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetchWithAuth("/support/tickets", {
        method: "POST",
        body: JSON.stringify({
          category,
          encrypted_payload: await encryptSupportPayload(
            { subject: subject.trim(), description: description.trim() },
            [cryptoContext!.ownPublicKey, cryptoContext!.adminPublicKey],
          ),
        }),
      });

      if (res.ok) {
        const created = (await res.json()) as Ticket;
        toast.success(`Request submitted. Reference AQ-${created.id.slice(0, 8).toUpperCase()}.`);
        setSubject("");
        setDescription("");
        setCategory("query");
        setExpandedTicket(created.id);
        await loadTickets();
        await loadTicketDetail(created.id);
      } else {
        throw new Error(`Ticket submission failed (${res.status})`);
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to submit ticket.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!encryption.ready || !cryptoContext) return encryption.panel;

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case "open":
        return "border-teal-700/30 bg-teal-100 text-teal-950 dark:border-teal-400/25 dark:bg-teal-400/10 dark:text-teal-200";
      case "waiting_user":
        return "border-amber-700/30 bg-amber-100 text-amber-950 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-200";
      case "in_progress":
        return "border-violet-700/30 bg-violet-100 text-violet-950 dark:border-violet-400/25 dark:bg-violet-400/10 dark:text-violet-200";
      case "resolved":
        return "border-emerald-700/30 bg-emerald-100 text-emerald-950 dark:border-emerald-400/25 dark:bg-emerald-400/10 dark:text-emerald-200";
      case "closed":
        return "border-border bg-surface-2 text-muted-foreground";
      default:
        return "border-border bg-surface-2 text-muted-foreground";
    }
  };

  return (
    <div className="dashboard-theme-scope support-page-theme w-full space-y-8 pb-12">
      {userDisabled && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-4 rounded-[2rem] border border-amber-600/25 bg-amber-50 p-6 dark:border-amber-400/20 dark:bg-amber-400/10"
        >
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300">
            <AlertCircle size={24} />
          </div>
          <div>
            <h4 className="text-xs font-bold tracking-wider text-amber-900 uppercase dark:text-amber-200">
              Account Restricted
            </h4>
            <p className="mt-1 text-sm text-amber-900/80 dark:text-amber-100/80">
              Your account is currently disabled. Please use this form to submit a request for
              reactivation or inquiry.
            </p>
          </div>
        </motion.div>
      )}
      <DashboardSectionHeader
        title="Support Center"
        subtitle="Global Resolution Gateway"
        icon={LifeBuoy}
        accentClassName="bg-purple-500 text-purple-500"
        accentGlowClassName="shadow-[0_0_20px_rgba(168,85,247,0.4)]"
        backHref="/dashboard"
        backLabel="Back To Dashboard"
      />

      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* Submit Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="theme-panel w-full rounded-2xl p-6 sm:p-8"
        >
          <div className="mb-8">
            <h2 className="text-foreground text-xl font-bold">How can we help?</h2>
            <p className="text-muted-foreground mt-2 text-sm">
              Submit your queries, feedback or complaints. Our team will get back to you shortly.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid gap-8 lg:grid-cols-2">
              <div className="space-y-2">
                <label className="text-muted-foreground text-xs font-bold tracking-[0.15em] uppercase">
                  Topic / Category
                </label>

                <RoundedSelect
                  label="Support ticket category"
                  value={category}
                  onChange={setCategory}
                  className="w-full"
                  triggerClassName="w-full px-4 py-3 text-sm"
                  options={supportCategories.map(([value, label]) => ({ value, label }))}
                />
              </div>

              <div className="space-y-2">
                <label className="text-muted-foreground text-xs font-bold tracking-[0.15em] uppercase">
                  Subject
                </label>
                <input
                  required
                  maxLength={255}
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Summarize your issue..."
                  className="support-form-control border-foreground/10 bg-foreground/5 text-foreground focus:border-primary/40 focus:ring-primary/20 w-full rounded-xl border px-4 py-3 text-sm transition outline-none focus:ring-1"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-muted-foreground text-xs font-bold tracking-[0.15em] uppercase">
                Detailed Description
              </label>
              <textarea
                required
                maxLength={20_000}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Please provide as much detail as possible..."
                rows={6}
                className="support-form-control border-foreground/10 bg-foreground/5 text-foreground focus:border-primary/40 focus:ring-primary/20 w-full resize-none rounded-2xl border px-4 py-4 text-sm transition outline-none focus:ring-1"
              />
            </div>

            <div className="flex justify-end pt-2">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                disabled={submitting}
                className="support-submit-button bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-2 rounded-xl px-8 py-3.5 text-sm font-bold shadow-[0_8px_16px_rgba(var(--primary),0.25)] transition disabled:opacity-50"
              >
                {submitting ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
                Submit Ticket
              </motion.button>
            </div>
          </form>
        </motion.div>

        {/* History Section */}
        <div className="space-y-6">
          <div className="theme-panel rounded-[2rem] p-6">
            <div className="mb-6 flex items-center gap-3">
              <History className="text-primary" size={20} />
              <h3 className="text-foreground text-sm font-bold tracking-[0.15em] uppercase">
                Recent Tickets
              </h3>
            </div>

            <div className="space-y-4">
              {loading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="text-primary animate-spin" size={24} />
                </div>
              ) : ticketListError ? (
                <div
                  role="alert"
                  className="rounded-2xl border border-rose-500/30 bg-rose-50 p-5 text-sm text-rose-900 dark:border-rose-400/25 dark:bg-rose-400/10 dark:text-rose-200"
                >
                  <p>{ticketListError}</p>
                  <button
                    type="button"
                    onClick={() => void loadTickets()}
                    className="mt-3 underline"
                  >
                    Retry
                  </button>
                </div>
              ) : tickets.length === 0 ? (
                <div className="bg-foreground/[0.03] border-foreground/10 rounded-2xl border border-dashed p-8 text-center">
                  <HelpCircle className="text-muted-foreground mx-auto mb-3" size={32} />
                  <p className="text-muted-foreground text-sm italic">No tickets submitted yet.</p>
                </div>
              ) : (
                tickets.map((ticket) => (
                  <div
                    key={ticket.id}
                    className="support-ticket-card group border-foreground/10 bg-foreground/[0.03] hover:border-primary/20 overflow-hidden rounded-2xl border transition"
                  >
                    <button
                      onClick={() => {
                        const next = expandedTicket === ticket.id ? null : ticket.id;
                        setExpandedTicket(next);
                        if (next) void loadTicketDetail(ticket.id);
                      }}
                      className="flex w-full items-start gap-4 p-4 text-left"
                    >
                      <div className="mt-1 flex flex-col items-center gap-1">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            ticket.status === "open"
                              ? "bg-teal-600"
                              : ticket.status === "waiting_user"
                                ? "bg-amber-500"
                                : ticket.status === "in_progress"
                                  ? "bg-violet-600"
                                  : ticket.status === "resolved"
                                    ? "bg-emerald-600"
                                    : "bg-slate-500"
                          }`}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-foreground truncate text-sm font-semibold">
                          {ticket.subject}
                        </p>

                        <div className="mt-2 flex items-center gap-2">
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-tighter uppercase ${getStatusColor(ticket.status)}`}
                          >
                            {ticket.status.replace("_", " ")}
                          </span>
                          <span className="text-muted-foreground text-[10px]">
                            {new Date(ticket.created_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                      <div className="text-muted-foreground group-hover:text-primary mt-1 transition-colors">
                        {expandedTicket === ticket.id ? (
                          <ChevronUp size={16} />
                        ) : (
                          <ChevronDown size={16} />
                        )}
                      </div>
                    </button>

                    <AnimatePresence initial={false}>
                      {expandedTicket === ticket.id && (
                        <motion.div
                          key={`support-thread-${ticket.id}`}
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2, ease: "easeInOut" }}
                          className="overflow-hidden"
                        >
                          <div className="support-ticket-thread text-muted-foreground border-foreground/5 bg-foreground/5 mt-2 space-y-4 border-t px-4 py-4 text-xs">
                            {ticketDetailErrors[ticket.id] && (
                              <div
                                role="alert"
                                className="flex items-center justify-between gap-3 text-red-400"
                              >
                                <span>{ticketDetailErrors[ticket.id]}</span>
                                <button
                                  type="button"
                                  onClick={() => void loadTicketDetail(ticket.id)}
                                  className="underline"
                                >
                                  Retry
                                </button>
                              </div>
                            )}
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-foreground/70 font-semibold">
                                Request AQ-{ticket.id.slice(0, 8).toUpperCase()}
                              </p>
                              <p>Priority: {ticket.priority}</p>
                            </div>
                            <p className="leading-relaxed whitespace-pre-wrap">
                              {ticket.description}
                            </p>
                            <div className="space-y-2">
                              <p className="text-foreground/70 font-semibold">Attachments</p>
                              {(ticketDetails[ticket.id]?.attachments ?? []).map((attachment) => (
                                <button
                                  key={attachment.id}
                                  type="button"
                                  onClick={() =>
                                    void openAttachment(
                                      attachment.download_url,
                                      attachment.filename,
                                      Boolean(attachment.is_encrypted),
                                      attachment.encrypted_metadata,
                                    )
                                  }
                                  className="border-border bg-background/70 text-foreground hover:border-primary/40 flex max-w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs"
                                >
                                  <Paperclip size={14} className="text-primary shrink-0" />
                                  <span className="truncate">{attachment.filename}</span>
                                  <span className="text-muted-foreground shrink-0">
                                    {(attachment.size_bytes / 1024).toFixed(0)} KB
                                  </span>
                                </button>
                              ))}
                              <label className="border-border text-foreground hover:border-primary/40 inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold">
                                <UploadCloud size={14} />{" "}
                                {uploadingAttachment
                                  ? "Uploading…"
                                  : "Attach PDF, PNG, JPEG, or TXT (max 5 MiB)"}
                                <input
                                  type="file"
                                  accept=".pdf,.png,.jpg,.jpeg,.txt"
                                  disabled={uploadingAttachment}
                                  className="sr-only"
                                  onChange={(event) => {
                                    void uploadAttachment(ticket.id, event.target.files?.[0]);
                                    event.currentTarget.value = "";
                                  }}
                                />
                              </label>
                              <p className="text-muted-foreground text-[11px] leading-5">
                                Attachments are encrypted before upload. AverQel cannot scan their
                                contents for malware; download only files you trust.
                              </p>
                            </div>
                            {(ticketDetails[ticket.id]?.messages ?? []).map((message) => {
                              const participant = ticketDetails[ticket.id]?.participants?.find(
                                (candidate) => candidate.ref === message.author_ref,
                              );
                              const authorLabel =
                                message.kind === "status_changed"
                                  ? "Status update"
                                  : message.author_role === "admin"
                                    ? "Support team"
                                    : "You";
                              return (
                                <article
                                  key={message.id}
                                  className="border-border bg-surface-1 text-foreground flex items-start gap-3 rounded-xl border p-3 shadow-sm"
                                >
                                  <ProfileAvatar
                                    avatar={
                                      participant?.avatar ??
                                      (message.author_role === "user" ? user?.avatar : null)
                                    }
                                    displayName={
                                      participant?.display_name ??
                                      (message.author_role === "user" ? user?.display_name : null)
                                    }
                                    fallbackLabel={authorLabel}
                                    className="h-9 w-9 rounded-xl"
                                  />
                                  <div className="min-w-0 flex-1">
                                    <div className="text-muted-foreground mb-1 flex flex-wrap items-center justify-between gap-2 text-[10px]">
                                      <span className="text-foreground font-semibold">
                                        {authorLabel}
                                      </span>
                                      <time>{new Date(message.created_at).toLocaleString()}</time>
                                    </div>
                                    <p className="whitespace-pre-wrap">{message.body}</p>
                                  </div>
                                </article>
                              );
                            })}
                            <form
                              onSubmit={(event) => {
                                event.preventDefault();
                                void handleReply(ticket.id);
                              }}
                              className="space-y-2"
                            >
                              <label
                                className="text-foreground/70 font-semibold"
                                htmlFor={`reply-${ticket.id}`}
                              >
                                Reply or add details
                              </label>
                              <textarea
                                id={`reply-${ticket.id}`}
                                maxLength={10_000}
                                value={replyDraft}
                                onChange={(event) => setReplyDraft(event.target.value)}
                                className="support-form-control border-foreground/10 bg-background text-foreground focus:border-primary/40 min-h-20 w-full rounded-xl border p-3 outline-none"
                                placeholder="Write a message to support…"
                              />
                              <div className="flex justify-end">
                                <button
                                  disabled={sendingReply || !replyDraft.trim()}
                                  className="support-reply-button bg-primary text-primary-foreground rounded-lg px-4 py-2 text-xs font-bold disabled:opacity-50"
                                >
                                  {sendingReply ? "Sending…" : "Send reply"}
                                </button>
                              </div>
                            </form>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Help Card */}
          <div className="support-priority-card bg-primary/10 border-primary/20 rounded-[2rem] border p-6">
            <div className="text-primary mb-3 flex items-center gap-3">
              <ShieldCheck size={20} />
              <h4 className="text-sm font-bold tracking-wider uppercase">Priority Support</h4>
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed font-medium">
              Normal-priority tickets have an 8-hour first-response target and a 72-hour resolution
              target. These are elapsed-time targets, not guarantees; waiting for your reply does
              not pause the resolution clock.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
