"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Star,
  Trophy,
  Sparkles,
  ChevronRight,
  Bug,
  FileText,
  Search,
  BrainCircuit,
  Cable,
  CreditCard,
  Gauge,
  ShieldCheck,
  Accessibility,
  Heart,
  MoreHorizontal,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import toast from "react-hot-toast";
import { fetchWithAuth } from "@/lib/api";

interface Campaign {
  id: string;
  title: string;
  description: string;
  created_at: string;
}

type FeedbackCategory =
  | "suggestion"
  | "bug"
  | "achievement"
  | "ux_improvement"
  | "documents_collections"
  | "query_quality"
  | "deepspace_agent"
  | "provider_integrations"
  | "billing_plan"
  | "performance"
  | "reliability"
  | "accessibility"
  | "security_privacy"
  | "positive_feedback"
  | "other";

interface FeedbackMessage {
  id: string;
  author_role: string;
  kind: string;
  body: string;
  created_at: string;
}

interface FeedbackSubmission {
  id: string;
  subject: string;
  content: string;
  category: FeedbackCategory;
  status: string;
  created_at: string;
  updated_at: string;
  messages: FeedbackMessage[];
}

const categories: Array<{
  id: FeedbackCategory;
  label: string;
  icon: React.ReactNode;
  color: string;
}> = [
  {
    id: "suggestion",
    label: "Product idea",
    icon: <Sparkles size={16} />,
    color: "text-amber-600",
  },
  { id: "bug", label: "Bug report", icon: <Bug size={16} />, color: "text-rose-600" },
  {
    id: "achievement",
    label: "Achievement",
    icon: <Trophy size={16} />,
    color: "text-emerald-700",
  },
  {
    id: "ux_improvement",
    label: "UX improvement",
    icon: <Star size={16} />,
    color: "text-blue-700",
  },
  {
    id: "documents_collections",
    label: "Documents & collections",
    icon: <FileText size={16} />,
    color: "text-cyan-700",
  },
  {
    id: "query_quality",
    label: "Query quality",
    icon: <Search size={16} />,
    color: "text-teal-700",
  },
  {
    id: "deepspace_agent",
    label: "DeepSpace agent",
    icon: <BrainCircuit size={16} />,
    color: "text-indigo-700",
  },
  {
    id: "provider_integrations",
    label: "Providers & integrations",
    icon: <Cable size={16} />,
    color: "text-violet-700",
  },
  {
    id: "billing_plan",
    label: "Plan & billing",
    icon: <CreditCard size={16} />,
    color: "text-orange-700",
  },
  { id: "performance", label: "Performance", icon: <Gauge size={16} />, color: "text-sky-700" },
  {
    id: "reliability",
    label: "Reliability",
    icon: <ShieldCheck size={16} />,
    color: "text-green-700",
  },
  {
    id: "accessibility",
    label: "Accessibility",
    icon: <Accessibility size={16} />,
    color: "text-purple-700",
  },
  {
    id: "security_privacy",
    label: "Security & privacy",
    icon: <ShieldCheck size={16} />,
    color: "text-red-700",
  },
  {
    id: "positive_feedback",
    label: "Positive feedback",
    icon: <Heart size={16} />,
    color: "text-pink-700",
  },
  { id: "other", label: "Other", icon: <MoreHorizontal size={16} />, color: "text-slate-700" },
];

import DashboardSectionHeader from "@/app/components/ui/DashboardSectionHeader";

export default function FeedbackPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [myFeedback, setMyFeedback] = useState<FeedbackSubmission[]>([]);
  const [expandedFeedback, setExpandedFeedback] = useState<string | null>(null);
  const [feedbackDetails, setFeedbackDetails] = useState<Record<string, FeedbackSubmission>>({});
  const [replyDraft, setReplyDraft] = useState("");
  const [sendingReply, setSendingReply] = useState(false);
  const [formData, setFormData] = useState({
    subject: "",
    content: "",
    category: "suggestion" as FeedbackCategory,
  });

  async function fetchCampaigns() {
    setLoading(true);
    setCampaignError(null);
    try {
      const res = await fetchWithAuth("/app-feedback/campaigns");
      if (!res.ok) throw new Error(`Could not load feedback campaigns (${res.status}).`);
      setCampaigns((await res.json()) as Campaign[]);
    } catch (err) {
      console.error("Failed to fetch campaigns", err);
      setCampaignError(err instanceof Error ? err.message : "Could not load feedback campaigns.");
    } finally {
      setLoading(false);
    }
  }

  async function fetchMyFeedback() {
    try {
      const res = await fetchWithAuth("/app-feedback/mine");
      if (!res.ok) throw new Error(`Failed to load feedback (${res.status})`);
      setMyFeedback((await res.json()) as FeedbackSubmission[]);
    } catch (err) {
      console.error("Failed to fetch submitted feedback", err);
    }
  }

  async function loadFeedbackDetail(id: string) {
    try {
      const res = await fetchWithAuth(`/app-feedback/mine/${id}`);
      if (!res.ok) throw new Error(`Failed to load feedback thread (${res.status})`);
      const detail = (await res.json()) as FeedbackSubmission;
      setFeedbackDetails((current) => ({ ...current, [id]: detail }));
    } catch (err) {
      console.error(err);
      toast.error("Could not load this feedback conversation.");
    }
  }

  async function sendFeedbackReply(id: string) {
    if (!replyDraft.trim()) return;
    setSendingReply(true);
    try {
      const res = await fetchWithAuth(`/app-feedback/mine/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ body: replyDraft.trim() }),
      });
      if (!res.ok) throw new Error(`Reply failed (${res.status})`);
      const detail = (await res.json()) as FeedbackSubmission;
      setFeedbackDetails((current) => ({ ...current, [id]: detail }));
      setMyFeedback((current) =>
        current.map((item) =>
          item.id === id ? { ...item, updated_at: detail.updated_at, status: detail.status } : item,
        ),
      );
      setReplyDraft("");
      toast.success("Reply sent.");
    } catch (err) {
      console.error(err);
      toast.error("Could not send your reply. Please try again.");
    } finally {
      setSendingReply(false);
    }
  }

  useEffect(() => {
    queueMicrotask(() => {
      void fetchCampaigns();
      void fetchMyFeedback();
    });
  }, []);

  useEffect(() => {
    const feedbackId = new URLSearchParams(window.location.search).get("feedback");
    if (feedbackId) {
      queueMicrotask(() => {
        setExpandedFeedback(feedbackId);
        void loadFeedbackDetail(feedbackId);
      });
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await fetchWithAuth("/app-feedback/submit", {
        method: "POST",
        body: JSON.stringify({
          ...formData,
          campaign_id: selectedCampaign?.id || null,
        }),
      });

      if (res.ok) {
        const created = (await res.json()) as FeedbackSubmission;
        setSuccess(true);
        setFormData({ subject: "", content: "", category: "suggestion" });
        setSelectedCampaign(null);
        setExpandedFeedback(created.id);
        await fetchMyFeedback();
        await loadFeedbackDetail(created.id);
        setTimeout(() => setSuccess(false), 5000);
      } else {
        throw new Error(`Feedback submission failed (${res.status})`);
      }
    } catch (err) {
      console.error("Submission failed", err);
      toast.error("Could not submit feedback. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full space-y-10">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <DashboardSectionHeader
          title="Feedback Center"
          subtitle="Help Us Shape The Future Of AverQel"
          icon={Sparkles}
          accentClassName="bg-amber-400 text-amber-400"
          accentGlowClassName="shadow-[0_0_20px_rgba(251,191,36,0.4)]"
          backHref="/dashboard"
          backLabel="Back To Dashboard"
        />
      </motion.div>

      <div className="grid min-w-0 grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* Feedback campaigns are optional prompts; personal submissions are listed below. */}
        <div className="min-w-0 space-y-6">
          <h2 className="flex items-center gap-2 text-xl font-semibold text-white/90">
            <Sparkles className="text-primary" size={20} />
            Feedback Campaigns
          </h2>

          {loading ? (
            <div className="flex h-32 items-center justify-center rounded-2xl border border-white/5 bg-white/[0.02]">
              <Loader2 className="text-primary animate-spin" size={24} />
            </div>
          ) : campaigns.length > 0 ? (
            <div className="space-y-4">
              {campaigns.map((c) => (
                <motion.button
                  key={c.id}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    setSelectedCampaign(c);
                    setFormData((prev) => ({ ...prev, subject: `Response to: ${c.title}` }));
                  }}
                  className={`w-full rounded-2xl border p-5 text-left transition-all ${
                    selectedCampaign?.id === c.id
                      ? "border-primary/50 bg-primary/10 shadow-[0_0_20px_rgba(var(--primary),0.1)]"
                      : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                  }`}
                >
                  <h3 className="mb-1 font-bold text-white">{c.title}</h3>
                  <p className="text-muted-foreground line-clamp-2 text-sm">{c.description}</p>
                  <div className="text-primary/70 mt-4 flex items-center gap-1 text-[10px] font-bold tracking-widest uppercase">
                    Respond Now <ChevronRight size={10} />
                  </div>
                </motion.button>
              ))}
            </div>
          ) : campaignError ? (
            <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-6 text-center">
              <p role="alert" className="text-foreground text-sm">
                {campaignError}
              </p>
              <button
                type="button"
                onClick={() => void fetchCampaigns()}
                className="border-border text-foreground hover:border-primary/40 mt-3 rounded-lg border px-3 py-2 text-xs font-semibold"
              >
                Try again
              </button>
            </div>
          ) : (
            <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
              <p className="text-muted-foreground text-sm">
                No campaigns are active right now. You can still submit feedback using the form.
              </p>
            </div>
          )}
        </div>

        <div className="min-w-0">
          <motion.div layout className="theme-panel rounded-2xl p-6 shadow-xl sm:p-8">
            <AnimatePresence mode="wait">
              {success ? (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  className="flex flex-col items-center justify-center py-20 text-center"
                >
                  <div className="mb-6 rounded-full bg-emerald-500/20 p-4 text-emerald-500 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
                    <CheckCircle2 size={48} />
                  </div>
                  <h2 className="text-foreground text-2xl font-bold">Thank You!</h2>
                  <p className="text-muted-foreground mt-2">
                    Your feedback has been submitted successfully. We appreciate your input!
                  </p>

                  <button
                    onClick={() => setSuccess(false)}
                    className="bg-foreground/10 text-foreground hover:bg-foreground/20 mt-8 rounded-xl px-6 py-2 text-sm font-semibold transition-all"
                  >
                    Send Another
                  </button>
                </motion.div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-8">
                  {selectedCampaign && (
                    <motion.div
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      className="bg-primary/10 border-primary/20 flex items-center justify-between rounded-xl border p-4"
                    >
                      <div>
                        <p className="text-primary text-[10px] font-bold tracking-widest uppercase">
                          Responding to request
                        </p>
                        <p className="text-foreground text-sm font-semibold">
                          {selectedCampaign.title}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCampaign(null);
                          setFormData((prev) => ({ ...prev, subject: "" }));
                        }}
                        className="text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Cancel
                      </button>
                    </motion.div>
                  )}

                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
                    {categories.map((cat) => (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => setFormData({ ...formData, category: cat.id })}
                        className={`flex min-h-12 items-center gap-2 rounded-xl border px-3 py-2 text-left transition-all ${
                          formData.category === cat.id
                            ? "border-primary/30 bg-primary/10 text-primary shadow-[0_0_15px_rgba(var(--primary),0.1)]"
                            : "border-foreground/10 bg-foreground/[0.02] hover:bg-foreground/[0.05]"
                        }`}
                      >
                        <span className={cat.color}>{cat.icon}</span>
                        <span
                          className={`text-xs font-bold ${formData.category === cat.id ? "text-primary" : "text-foreground"}`}
                        >
                          {cat.label}
                        </span>
                      </button>
                    ))}
                  </div>

                  <div className="space-y-6">
                    <div className="space-y-2">
                      <label className="text-muted-foreground text-xs font-bold tracking-widest uppercase">
                        Subject
                      </label>
                      <input
                        required
                        value={formData.subject}
                        onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                        placeholder="What's on your mind?"
                        className="border-foreground/10 bg-foreground/[0.02] text-foreground placeholder:text-muted-foreground/30 focus:border-primary/50 focus:bg-foreground/[0.05] w-full rounded-xl border p-4 transition-all focus:outline-none"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-muted-foreground text-xs font-bold tracking-widest uppercase">
                        Description
                      </label>
                      <textarea
                        required
                        rows={6}
                        value={formData.content}
                        onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                        placeholder="Tell us more about your suggestion, bug, or achievement..."
                        className="border-foreground/10 bg-foreground/[0.02] text-foreground placeholder:text-muted-foreground/30 focus:border-primary/50 focus:bg-foreground/[0.05] w-full resize-none rounded-2xl border p-4 transition-all focus:outline-none"
                      />
                    </div>
                  </div>

                  <button
                    disabled={submitting}
                    className="bg-primary flex w-full items-center justify-center gap-2 rounded-2xl py-4 font-black !text-white shadow-[0_0_20px_rgba(var(--primary),0.2)] transition-all hover:shadow-[0_0_30px_rgba(var(--primary),0.3)] active:scale-[0.99] disabled:opacity-50"
                  >
                    {submitting ? (
                      <Loader2 className="animate-spin !text-white" size={20} />
                    ) : (
                      <Send className="!text-white" size={20} />
                    )}
                    Submit Feedback
                  </button>
                </form>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </div>

      <section className="theme-panel rounded-2xl p-5 sm:p-7" aria-label="My feedback history">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-foreground text-lg font-bold">My feedback</h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Track review progress and continue a conversation with the AverQel team.
            </p>
          </div>
          <span className="theme-chip rounded-lg px-3 py-1.5 text-xs">
            {myFeedback.length} submissions
          </span>
        </div>
        {myFeedback.length === 0 ? (
          <div className="border-foreground/10 text-muted-foreground rounded-xl border border-dashed px-4 py-8 text-center text-sm">
            Your submitted feedback and team replies will appear here.
          </div>
        ) : (
          <div className="space-y-3">
            {myFeedback.map((submission) => {
              const detail = feedbackDetails[submission.id];
              const expanded = expandedFeedback === submission.id;
              return (
                <article
                  key={submission.id}
                  className="border-foreground/10 bg-background/50 overflow-hidden rounded-xl border"
                >
                  <button
                    type="button"
                    onClick={() => {
                      const next = expanded ? null : submission.id;
                      setExpandedFeedback(next);
                      if (next) void loadFeedbackDetail(submission.id);
                    }}
                    className="flex w-full items-center justify-between gap-4 p-4 text-left"
                  >
                    <span className="min-w-0">
                      <span className="text-foreground block truncate text-sm font-semibold">
                        {submission.subject}
                      </span>
                      <span className="text-muted-foreground mt-1 block text-xs">
                        {submission.category.replaceAll("_", " ")} · Updated{" "}
                        {new Date(submission.updated_at).toLocaleDateString()}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="theme-chip rounded-full px-2.5 py-1 text-[10px] font-bold capitalize">
                        {submission.status.replaceAll("_", " ")}
                      </span>
                      <ChevronRight
                        size={15}
                        className={`text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`}
                      />
                    </span>
                  </button>
                  <AnimatePresence initial={false}>
                    {expanded && (
                      <motion.div
                        key={`feedback-thread-${submission.id}`}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2, ease: "easeInOut" }}
                        className="overflow-hidden"
                      >
                        <div className="border-foreground/10 space-y-3 border-t p-4">
                          <p className="text-muted-foreground text-sm whitespace-pre-wrap">
                            {submission.content}
                          </p>
                          {(detail?.messages ?? []).map((message) => (
                            <div
                              key={message.id}
                              className="border-foreground/10 bg-surface-1 rounded-xl border p-3"
                            >
                              <div className="text-muted-foreground mb-1 flex justify-between gap-3 text-[10px]">
                                <span className="text-foreground font-semibold">
                                  {message.kind === "status_changed"
                                    ? "Status update"
                                    : message.author_role === "admin"
                                      ? "AverQel team"
                                      : "You"}
                                </span>
                                <time>{new Date(message.created_at).toLocaleString()}</time>
                              </div>
                              <p className="text-foreground text-sm whitespace-pre-wrap">
                                {message.body}
                              </p>
                            </div>
                          ))}
                          <form
                            onSubmit={(event) => {
                              event.preventDefault();
                              void sendFeedbackReply(submission.id);
                            }}
                            className="flex flex-col gap-2 sm:flex-row sm:items-end"
                          >
                            <label className="sr-only" htmlFor={`feedback-reply-${submission.id}`}>
                              Reply to feedback
                            </label>
                            <textarea
                              id={`feedback-reply-${submission.id}`}
                              maxLength={10_000}
                              rows={2}
                              value={replyDraft}
                              onChange={(event) => setReplyDraft(event.target.value)}
                              placeholder="Add details or reply to the team…"
                              className="border-foreground/10 bg-background text-foreground focus:border-primary/40 placeholder:text-muted-foreground min-h-16 min-w-0 flex-1 resize-y rounded-xl border px-3 py-2.5 text-sm outline-none"
                            />
                            <button
                              disabled={sendingReply || !replyDraft.trim()}
                              className="bg-primary text-primary-foreground shrink-0 rounded-xl px-4 py-2.5 text-xs font-bold disabled:opacity-50"
                            >
                              {sendingReply ? "Sending…" : "Send reply"}
                            </button>
                          </form>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
